"""
Email Organizer — Claude-powered inbox categorization, labeling, and cleanup.

Classifies emails into categories (Business, Personal, Tax, etc.),
applies Gmail labels, and archives/trashes junk mail.

Works on both historical inbox cleanup and ongoing new-email triage.
"""
import json
import logging
import anthropic
from datetime import date

log = logging.getLogger("organizer")

# ── Categories ──────────────────────────────────────────────────────────────

# Keep categories — these get a Gmail label under "Organized/<name>"
KEEP_CATEGORIES = [
    "Business",
    "Personal",
    "Tax",
    "Fees",
    "Government",
    "Product Purchases",
    "Licenses and Keys",
    "Finance",
    "Health and Insurance",
    "Travel",
    "Legal",
    "Education",
    "Employment",
    "Shipping and Delivery",
    "Account Security",
    "Important",
]

# Junk categories — these get archived or trashed
JUNK_CATEGORIES = [
    "Marketing",
    "Newsletter",
    "Promotional",
    "Spam",
    "Social Notification",
    "Automated Alert",
]

ALL_CATEGORIES = KEEP_CATEGORIES + JUNK_CATEGORIES

CLASSIFICATION_SYSTEM_PROMPT = """You are an email triage assistant. Your job is to classify emails into categories so the user's inbox stays clean and organized.

OWNER: {owner_name}
OWNER'S EMAIL ACCOUNTS: {account_emails}

## KEEP categories (important — label and keep in inbox or archive neatly):
- Business: Work-related, client communications, invoices, contracts, B2B
- Personal: Friends, family, personal correspondence
- Tax: Tax documents, W-2s, 1099s, tax prep, IRS communications
- Fees: Bills, subscription charges, payment confirmations, bank fees
- Government: DMV, city/county/state/federal agencies, voter info, jury duty
- Product Purchases: Order confirmations, receipts, warranty info, product registrations
- Licenses and Keys: Software licenses, product keys, activation codes, serial numbers, digital purchases
- Finance: Banking, investments, credit cards, loan statements, financial advisors
- Health and Insurance: Medical, dental, vision, prescriptions, insurance policies, claims
- Travel: Flight confirmations, hotel bookings, car rentals, itineraries
- Legal: Contracts, agreements, legal notices, attorney correspondence
- Education: Courses, certifications, training, academic correspondence
- Employment: Job-related, HR, payroll, benefits, W-2
- Shipping and Delivery: Package tracking, delivery notifications, shipping confirmations
- Account Security: Password resets, 2FA codes, security alerts, login notifications
- Important: Anything important that doesn't fit neatly into the above categories

## JUNK categories (archive or trash):
- Marketing: Sales pitches, promotional offers, discount codes, "limited time" offers
- Newsletter: Email newsletters, digests, blog updates, content roundups
- Promotional: Deals, coupons, store announcements, product launches
- Spam: Unsolicited junk, scams, phishing attempts
- Social Notification: Social media alerts (likes, follows, friend requests), forum notifications
- Automated Alert: Automated system notifications that aren't security-related, build alerts, CI/CD, monitoring noise

## Rules:
1. If an email could fit multiple categories, choose the MOST SPECIFIC one
2. Order confirmations/receipts → "Product Purchases" (not Marketing, even if from a store)
3. Password resets and 2FA → "Account Security" (not Spam)
4. Bank statements → "Finance" (not Fees)
5. Tax-related from employer → "Tax" (not Employment)
6. A subscription CHARGE/receipt → "Fees"; a subscription PROMO → "Marketing"
7. Shipping updates for a real order → "Shipping and Delivery" (not Marketing)
8. License keys or activation emails → "Licenses and Keys"
9. When in doubt between keep and junk, lean toward KEEP — false negatives (missing important mail) are worse than false positives

Today's date: {today}

Respond with valid JSON only."""

CLASSIFICATION_USER_PROMPT = """Classify each email below. For each, provide:
- category: one of {categories}
- action: "label" (apply category label, keep accessible), "archive" (label + remove from inbox), or "trash" (delete)
- confidence: "high", "medium", or "low"

Guidelines for action:
- "label": Important emails the user may want to reference or act on (keep in inbox)
- "archive": Emails worth keeping for records but not needing inbox attention — OR junk that might have opt-out value
- "trash": Clear spam, phishing, or truly worthless junk

EMAILS:
{emails_json}

Respond with a JSON object mapping email IDs to classifications:
{{
  "<email_id>": {{
    "category": "<category>",
    "action": "<label|archive|trash>",
    "confidence": "<high|medium|low>",
    "reason": "<1 sentence why>"
  }}
}}"""


class EmailOrganizer:
    """Classifies emails using Claude and applies Gmail labels/actions."""

    def __init__(
        self,
        owner_name: str,
        account_emails: list[str],
        model: str = "claude-sonnet-4-6",
        batch_size: int = 25,
    ):
        self.client = anthropic.Anthropic()
        self.owner_name = owner_name
        self.account_emails = account_emails
        self.model = model
        self.batch_size = batch_size

    def classify_batch(self, emails: list[dict]) -> dict:
        """Send a batch of emails to Claude for classification.

        Returns dict mapping email_id → {category, action, confidence, reason}.
        """
        if not emails:
            return {}

        emails_for_prompt = []
        for e in emails:
            emails_for_prompt.append({
                "id": e["id"],
                "sender": e.get("sender", ""),
                "recipients": e.get("recipients", []),
                "subject": e.get("subject", ""),
                "date": e.get("date", ""),
                "body_snippet": e.get("body_snippet", "")[:1200],
                "labels": e.get("labels", []),
            })

        system_prompt = CLASSIFICATION_SYSTEM_PROMPT.format(
            owner_name=self.owner_name,
            account_emails=", ".join(self.account_emails),
            today=date.today().isoformat(),
        )

        user_prompt = CLASSIFICATION_USER_PROMPT.format(
            categories=", ".join(ALL_CATEGORIES),
            emails_json=json.dumps(emails_for_prompt, indent=2),
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        for block in response.content:
            if block.type == "text":
                return self._parse_json(block.text)

        return {}

    def classify_and_act(self, emails: list[dict], gmail_client, dry_run: bool = False) -> dict:
        """Classify a batch of emails and apply Gmail labels/actions.

        Returns summary stats: {labeled, archived, trashed, skipped, errors}.
        """
        stats = {"labeled": 0, "archived": 0, "trashed": 0, "skipped": 0, "errors": 0}
        classifications = self.classify_batch(emails)

        email_map = {e["id"]: e for e in emails}

        for email_id, result in classifications.items():
            category = result.get("category", "Important")
            action = result.get("action", "label")
            confidence = result.get("confidence", "medium")

            # Safety: never trash with low confidence
            if action == "trash" and confidence == "low":
                action = "archive"

            if dry_run:
                subj = email_map.get(email_id, {}).get("subject", "?")
                log.info(f"[DRY RUN] {email_id}: {category} → {action} ({confidence}) — {subj}")
                stats["labeled"] += 1
                continue

            try:
                # Apply category label
                if category in KEEP_CATEGORIES:
                    label_name = f"Organized/{category}"
                else:
                    label_name = f"Organized/Junk/{category}"

                label_id = gmail_client.get_or_create_label(label_name)

                if action == "trash":
                    # Label first so it's categorized even in trash
                    gmail_client.apply_label(email_id, label_id)
                    gmail_client.trash_email(email_id)
                    stats["trashed"] += 1
                elif action == "archive":
                    gmail_client.apply_labels_and_actions(
                        email_id,
                        add_label_ids=[label_id],
                        remove_label_ids=["INBOX"],
                    )
                    stats["archived"] += 1
                else:  # "label"
                    gmail_client.apply_label(email_id, label_id)
                    stats["labeled"] += 1

            except Exception as e:
                log.warning(f"Failed to process {email_id}: {e}")
                stats["errors"] += 1

        stats["skipped"] = len(emails) - sum(
            stats[k] for k in ("labeled", "archived", "trashed", "errors")
        )
        return stats, classifications

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {}
