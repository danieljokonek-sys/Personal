"""
Email Organizer — Claude-powered inbox categorization, labeling, and cleanup.

Classifies emails into categories (business entities, personal, tax, etc.),
applies Gmail labels, and archives/trashes junk mail.

Works on both historical inbox cleanup and ongoing new-email triage.
"""
import json
import logging
import anthropic
from datetime import date

log = logging.getLogger("organizer")

# ── Categories ──────────────────────────────────────────────────────────────

# Business entity labels — each gets its own top-level Gmail label
BUSINESS_CATEGORIES = [
    "Audio Services",
    "Terra Cognita",
    "Well Made Plays",
    "The Chorus Crafters",
    "4400 Mount Vernon Drive",
]

# General keep categories
KEEP_CATEGORIES = [
    "Personal",
    "Tax",
    "Fees and Bills",
    "Government",
    "Politics",
    "Product Purchases",
    "Product Downloads",
    "Licenses and Keys",
    "Finance",
    "Health and Insurance",
    "Travel",
    "Legal",
    "Education",
    "Employment",
    "Shipping and Delivery",
    "Account Security",
    "Logins and Verification",
    "Important",
]

# Junk categories — archived or trashed
JUNK_CATEGORIES = [
    "Marketing",
    "Newsletter",
    "Promotional",
    "Spam",
    "Social Notification",
    "Automated Alert",
    "Political Junk",
]

ALL_CATEGORIES = BUSINESS_CATEGORIES + KEEP_CATEGORIES + JUNK_CATEGORIES

CLASSIFICATION_SYSTEM_PROMPT = """You are an email triage assistant. Your job is to classify emails into categories so the user's inbox stays clean and organized.

OWNER: {owner_name}
OWNER'S EMAIL ACCOUNTS: {account_emails}

## BUSINESS ENTITY categories (the owner's businesses — each gets its own label):
- Audio Services: Daniel's freelance audio engineering, recording, mixing, mastering, and production work for external clients (NOT Terra Cognita band work)
- Terra Cognita: Everything related to Daniel's band Terra Cognita — gigs, shows, rehearsals, band member communications, booking inquiries, setlists, merch, social media for the band. Email account: terracognitamusic@gmail.com
- Well Made Plays: Music management and events company co-run with Douglas Schmidt (Doug Schmidt). Bookings, venue deals, artist management, event logistics, revenue splits, contracts
- The Chorus Crafters: Custom song company — commissions, client orders, song delivery, revisions, demos, deposits, payments for personalized songs (weddings, memorials, birthdays). Co-run with Dan Hochman. Email account: thechoruscrafters@gmail.com
- 4400 Mount Vernon Drive: Rental property — tenants, rent, leases, maintenance, repairs, property tax, HOA, contractors, property management

## KEEP categories (important — label and keep):
- Personal: Friends, family, personal correspondence, personal plans
- Tax: Tax documents, W-2s, 1099s, tax prep, IRS, state tax agencies, CPA correspondence, estimated tax payments, tax refunds
- Fees and Bills: Subscription charges, utility bills, payment confirmations, bank fees, service charges, recurring charges, invoices you owe
- Government: DMV, city/county/state/federal agencies, voter registration, jury duty, census, government benefits, USPS, passport
- Politics: Genuine political correspondence — emails from elected officials or representatives you've contacted, policy updates from YOUR representatives, town hall invitations, constituent services, ballot/election info from official sources. NOT mass fundraising or campaign blasts
- Product Purchases: Order confirmations, purchase receipts, warranty info, product registrations, digital and physical purchases from stores
- Product Downloads: Software downloads, app purchase confirmations, digital product delivery, download links, installer access
- Licenses and Keys: Software license keys, product activation codes, serial numbers, registration codes, API keys, certificate files, digital entitlements, license renewal notices
- Finance: Banking, investment statements, credit card statements, loan documents, Fidelity, brokerage, 401k, financial advisors, Found banking
- Health and Insurance: Medical, dental, vision, prescriptions, insurance policies and claims, doctor correspondence, lab results, EOBs
- Travel: Flight confirmations, boarding passes, hotel reservations, Airbnb, car rental confirmations, trip itineraries, travel insurance, TSA, airline communications, rental car receipts
- Legal: Contracts, legal notices, attorney correspondence, lawsuits, legal agreements, terms changes from important services
- Education: Courses, certifications, training, academic correspondence, online learning platforms
- Employment: Job-related (when Daniel is the employee), HR, payroll, benefits enrollment
- Shipping and Delivery: Package tracking, delivery notifications, shipping confirmations, carrier updates (UPS, FedEx, USPS, Amazon delivery)
- Account Security: Password resets, two-factor authentication codes, security alerts, breach notifications, recovery codes, backup codes
- Logins and Verification: Email verification, account verification, new device sign-ins, login confirmations, identity verification, "confirm your email" messages
- Important: Anything clearly important that doesn't fit the above categories

## JUNK categories (archive or trash):
- Marketing: Sales pitches, promotional offers, discount codes, "limited time" offers, upsell emails, "we miss you" re-engagement
- Newsletter: Email newsletters, weekly digests, blog updates, content roundups, industry news, "your week in review" from non-financial services
- Promotional: Deals, coupons, store announcements, product launches, Black Friday, seasonal sales
- Spam: Unsolicited junk, scams, phishing, lottery winners, Nigerian princes
- Social Notification: Social media alerts (LinkedIn, Facebook, Instagram, Twitter likes/follows/comments), forum notifications, community digests
- Automated Alert: Non-critical automated system notifications, CI/CD build alerts, monitoring noise, usage stats from free-tier services, "welcome to X" onboarding drip campaigns
- Political Junk: Mass campaign fundraising blasts, PAC solicitations, "will you chip in $5?" emails, bulk political petitions, campaign auto-mailers with unsubscribe links, candidate endorsement spam. Telltale signs: sent via bulk email platforms (e.g. ActionKit, NGP VAN, Mailchimp), generic "Dear supporter" tone, urgency-driven donation asks, large unsubscribe footers

## CRITICAL RULES:
1. BUSINESS ENTITY FIRST: If an email clearly relates to one of the 5 business entities, use that entity category — even if it also fits a general category
2. Order confirmations/receipts → "Product Purchases" (NOT Marketing, even if from a store)
3. Password resets, 2FA codes, new device logins → "Account Security" or "Logins and Verification" (NEVER Spam or Junk)
4. Software license keys, activation codes, serial numbers → "Licenses and Keys" (NEVER Marketing)
5. Software/app download confirmations → "Product Downloads" (NEVER Automated Alert)
6. Flight/hotel/car rental confirmations → "Travel" (NEVER Marketing, even from travel companies)
7. Bank/investment statements → "Finance" (NOT Fees)
8. Tax-related from any source → "Tax" (overrides Employment, Finance, etc.)
9. A subscription CHARGE/receipt → "Fees and Bills"; a subscription PROMO → "Marketing"
10. Shipping tracking for a real order → "Shipping and Delivery" (NOT Marketing)
11. Emails FROM the owner TO the owner (self-sends, forwarded texts) → classify by CONTENT, not as Personal
12. PayPal/Venmo payment receipts → categorize by WHAT was paid for (Canva = "Fees and Bills", band gear = "Terra Cognita", etc.)
13. Legal agreement changes from services you use (PayPal TOS, etc.) → "Legal"
14. Found banking weekly reviews for Terra Cognita → "Finance" (NOT Newsletter — it's a real bank statement)
15. POLITICAL EMAILS — distinguish carefully:
    - Personal/direct correspondence from a politician or their office → "Politics" (KEEP)
    - Official government/election notices → "Government" (KEEP)
    - Town halls, constituent updates from YOUR representatives → "Politics" (KEEP)
    - Mass fundraising blasts ("chip in $5", "match my donation", "deadline midnight") → "Political Junk" (ARCHIVE)
    - Campaign auto-mailers with bulk unsubscribe links, sent via email platforms → "Political Junk" (ARCHIVE)
    - If it reads like a personal reply or direct constituent communication → KEEP as "Politics"
    - If it reads like it was sent to 100,000 people → "Political Junk"
16. When in doubt between keep and junk, ALWAYS lean toward KEEP

Today's date: {today}

Respond with valid JSON only."""

CLASSIFICATION_USER_PROMPT = """Classify each email below. For each, provide:
- category: one of {categories}
- action: "label" (apply category label, keep accessible), "archive" (label + remove from inbox), or "trash" (delete)
- confidence: "high", "medium", or "low"

Guidelines for action:
- "label": Important emails the user should see or reference — business, financial, security, travel, licenses, personal
- "archive": Emails worth keeping for records but not needing inbox attention — OR junk with opt-out value
- "trash": Clear spam, phishing, or truly worthless junk with zero reference value

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

        Returns (stats, classifications).
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
                label_name = self._label_name_for_category(category)
                label_id = gmail_client.get_or_create_label(label_name)

                if action == "trash":
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

    @staticmethod
    def _label_name_for_category(category: str) -> str:
        """Map a category to a Gmail label path.

        Business entities get top-level labels.
        General keep categories go under Organized/.
        Junk categories go under Organized/Junk/.
        """
        if category in BUSINESS_CATEGORIES:
            return category  # top-level: "Terra Cognita", "The Chorus Crafters", etc.
        elif category in JUNK_CATEGORIES:
            return f"Organized/Junk/{category}"
        else:
            return f"Organized/{category}"

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
