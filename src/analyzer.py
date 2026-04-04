"""
Claude-powered email analysis engine.

Processes batches of emails through Claude to extract:
- Agreements and commitments
- Deadlines and due dates
- Financial obligations (who owes what, to which entity)
- Action items
"""
import json
import anthropic
from datetime import date

from .entities import Entity


EXTRACTION_SYSTEM_PROMPT = """You are a personal assistant AI that analyzes email communications for a musician/entrepreneur who runs multiple businesses:

BUSINESS ENTITIES:
{entities_description}

IMPORTANT CONTEXT ABOUT EACH BUSINESS:
- The Chorus Crafters: A custom song company. Clients commission personalized songs for weddings, memorials, birthdays, and other life events. The owner writes, produces, mixes, and masters each song. Revenue comes from song orders/commissions. Look for: client intake info (names, story, song details), order confirmations, revision requests, delivery confirmations, payment for song orders, deadlines for event dates.
- Terra Cognita: A working band and audio services business. Revenue from gigs/shows, session work, audio production for clients. Look for: booking inquiries, contracts, show details, payment for performances or audio work.
- Well Made Plays: Music management and events company, co-run with Douglas Schmidt. Look for: management contracts, event logistics, venue deals, artist agreements, revenue splits with Douglas.
- 4400 Mount Vernon Drive: A rental property. Revenue is rent. Expenses are maintenance, repairs, taxes. Look for: rent payments, lease terms, tenant communications, maintenance requests, contractor quotes.

YOUR JOB: Analyze each email and extract any actionable information. Be thorough but precise — only extract items that are clearly stated or strongly implied in the communication. Do not fabricate or speculate.

For financial items:
- "receivable" = money owed TO the owner (someone should pay them)
- "payable" = money the owner owes to someone else
- Always try to identify which business entity the financial item relates to
- Include the counterparty name (who owes or is owed)
- For Chorus Crafters: a song commission = receivable; paying a session musician = payable

For deadlines:
- Extract specific dates when mentioned (wedding date, event date, delivery deadline, rent due date)
- Flag urgency based on how close the deadline is
- Priority: "high" for < 3 days or explicit urgency, "medium" for < 2 weeks, "low" otherwise

For agreements:
- Capture any commitments, verbal contracts, promises made in either direction
- For Chorus Crafters: note song details (event type, names involved, style, revisions included)
- Note the parties involved

For action items:
- Things the owner needs to do or follow up on
- Things others have committed to doing

If an email is purely social, a newsletter, or marketing — return empty arrays for all fields. Don't force-fit items that aren't there.

Today's date is {today}.

Respond with valid JSON only."""


EXTRACTION_USER_PROMPT = """Analyze these emails and extract actionable items. For each email, determine which business entity (if any) it relates to, and extract agreements, deadlines, financial items, and action items.

Entity keys to use: {entity_keys}
If an item doesn't clearly relate to any entity, use "personal" as the entity_key.

EMAILS TO ANALYZE:
{emails_json}

Respond with a JSON object mapping email IDs to their extractions:
{{
  "<email_id>": {{
    "entity_key": "<best matching entity key or 'personal'>",
    "summary": "<1-2 sentence summary of what this email is about>",
    "agreements": [
      {{
        "entity_key": "<entity>",
        "summary": "<what was agreed>",
        "parties": ["<name1>", "<name2>"],
        "terms": "<key terms if any>",
        "source_date": "<YYYY-MM-DD>"
      }}
    ],
    "deadlines": [
      {{
        "entity_key": "<entity>",
        "description": "<what is due>",
        "due_date": "<YYYY-MM-DD or null>",
        "priority": "<high|medium|low>",
        "source_date": "<YYYY-MM-DD>"
      }}
    ],
    "financial_items": [
      {{
        "entity_key": "<entity>",
        "direction": "<receivable|payable>",
        "counterparty": "<name of person/org>",
        "amount": <number or null>,
        "currency": "USD",
        "description": "<what it's for>",
        "due_date": "<YYYY-MM-DD or null>",
        "source_date": "<YYYY-MM-DD>"
      }}
    ],
    "action_items": [
      {{
        "entity_key": "<entity>",
        "description": "<what needs to be done>",
        "assigned_to": "<who should do it>",
        "due_date": "<YYYY-MM-DD or null>",
        "priority": "<high|medium|low>",
        "source_date": "<YYYY-MM-DD>"
      }}
    ]
  }}
}}

Only include items that are clearly present in the emails. Empty arrays are fine."""


class Analyzer:
    def __init__(self, entities: dict[str, Entity], model: str = "claude-opus-4-6"):
        self.client = anthropic.Anthropic()
        self.entities = entities
        self.model = model

    def _build_entities_description(self) -> str:
        parts = []
        for key, entity in self.entities.items():
            desc = f"- {entity.name} (key: {key}): {entity.description}"
            if entity.partner:
                desc += f" — partner: {entity.partner}"
            parts.append(desc)
        return "\n".join(parts)

    def analyze_batch(self, emails: list[dict]) -> dict:
        """Analyze a batch of emails and return extractions keyed by email ID."""
        if not emails:
            return {}

        entities_desc = self._build_entities_description()
        entity_keys = list(self.entities.keys()) + ["personal"]

        emails_for_prompt = []
        for e in emails:
            emails_for_prompt.append({
                "id": e["id"],
                "sender": e.get("sender", ""),
                "recipients": e.get("recipients", []),
                "subject": e.get("subject", ""),
                "date": e.get("date", ""),
                "body_snippet": e.get("body_snippet", "")[:1500],
            })

        system_prompt = EXTRACTION_SYSTEM_PROMPT.format(
            entities_description=entities_desc,
            today=date.today().isoformat(),
        )

        user_prompt = EXTRACTION_USER_PROMPT.format(
            entity_keys=", ".join(entity_keys),
            emails_json=json.dumps(emails_for_prompt, indent=2),
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Extract JSON from response
        for block in response.content:
            if block.type == "text":
                return self._parse_json_response(block.text)

        return {}

    def _parse_json_response(self, text: str) -> dict:
        """Parse JSON from Claude's response, handling markdown code blocks."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Drop first and last lines (```json and ```)
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {}

    def generate_digest_analysis(self, digest_data: dict) -> str:
        """Use Claude to generate a natural-language digest summary."""
        system_prompt = """You are a sharp, concise personal assistant writing a daily briefing email for a musician/entrepreneur. Write in a warm but direct tone — like a trusted chief of staff who knows the business well.

Business entities:
{entities}

Format the briefing as clean HTML for email. Use headers, bullet points, and bold for emphasis. Keep it scannable — busy people need to see the important stuff immediately.

Sections to include (skip any section with nothing to report):
1. URGENT (anything due today or overdue)
2. Money Matters (who owes what, what's due)
3. This Week's Deadlines
4. Active Agreements to Track
5. Action Items
6. Quick Stats""".format(entities=self._build_entities_description())

        user_prompt = f"""Generate today's briefing from this data:

{json.dumps(digest_data, indent=2, default=str)}

Today is {date.today().isoformat()}. Write the HTML email body."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        for block in response.content:
            if block.type == "text":
                return block.text

        return "<p>No digest generated.</p>"
