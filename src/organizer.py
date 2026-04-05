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

# All keep categories — the classifier outputs these names,
# then _label_name_for_category() maps them to nested Gmail labels.
KEEP_CATEGORIES = [
    # Business
    "Audio Services",
    "Terra Cognita",
    "Well Made Plays",
    "The Chorus Crafters",
    # Property
    "4400 Mount Vernon Drive",
    "2300 Southern Oaks",
    # Finance
    "Tax",
    "Fees and Bills",
    "Banking and Investments",
    # Legal & Government
    "Legal",
    "Government",
    "Politics",
    # Shopping
    "Product Purchases",
    "Product Downloads",
    "Licenses and Keys",
    "Shipping and Delivery",
    # Security
    "Account Security",
    "Logins and Verification",
    # Health & Travel
    "Health and Insurance",
    "Travel",
    # Personal
    "Personal",
    "Education",
    "Employment",
]

# Junk — auto-deleted, no label created
JUNK_CATEGORIES = [
    "Junk",
]

ALL_CATEGORIES = KEEP_CATEGORIES + JUNK_CATEGORIES

# Category → nested Gmail label path
LABEL_PATH_MAP = {
    # Business/
    "Audio Services":           "Business/Audio Services",
    "Terra Cognita":            "Business/Terra Cognita",
    "Well Made Plays":          "Business/Well Made Plays",
    "The Chorus Crafters":      "Business/The Chorus Crafters",
    # Property/
    "4400 Mount Vernon Drive":  "Property/4400 Mount Vernon Drive",
    "2300 Southern Oaks":       "Property/2300 Southern Oaks",
    # Finance/
    "Tax":                      "Finance/Tax",
    "Fees and Bills":           "Finance/Fees and Bills",
    "Banking and Investments":  "Finance/Banking and Investments",
    # Legal & Government/
    "Legal":                    "Legal & Government/Legal",
    "Government":               "Legal & Government/Government",
    "Politics":                 "Legal & Government/Politics",
    # Shopping/
    "Product Purchases":        "Shopping/Product Purchases",
    "Product Downloads":        "Shopping/Product Downloads",
    "Licenses and Keys":        "Shopping/Licenses and Keys",
    "Shipping and Delivery":    "Shopping/Shipping and Delivery",
    # Security/
    "Account Security":         "Security/Account Security",
    "Logins and Verification":  "Security/Logins and Verification",
    # Health & Travel/
    "Health and Insurance":     "Health & Travel/Health and Insurance",
    "Travel":                   "Health & Travel/Travel",
    # Personal/
    "Personal":                 "Personal/Personal",
    "Education":                "Personal/Education",
    "Employment":               "Personal/Employment",
}

# Gmail label colors — must use ONLY hex values from Gmail's allowed palette.
LABEL_COLORS = {
    # Business — bold, distinct
    "Business/Audio Services":           {"textColor": "#ffffff", "backgroundColor": "#fb4c2f"},  # red
    "Business/Terra Cognita":            {"textColor": "#ffffff", "backgroundColor": "#16a765"},  # green
    "Business/Well Made Plays":          {"textColor": "#ffffff", "backgroundColor": "#4a86e8"},  # blue
    "Business/The Chorus Crafters":      {"textColor": "#ffffff", "backgroundColor": "#ffad47"},  # orange
    # Property
    "Property/4400 Mount Vernon Drive":  {"textColor": "#ffffff", "backgroundColor": "#a479e2"},  # purple
    "Property/2300 Southern Oaks":       {"textColor": "#ffffff", "backgroundColor": "#8e63ce"},  # dark purple
    # Finance
    "Finance/Tax":                       {"textColor": "#ffffff", "backgroundColor": "#b65775"},  # rose
    "Finance/Fees and Bills":            {"textColor": "#ffffff", "backgroundColor": "#e07798"},  # pink
    "Finance/Banking and Investments":   {"textColor": "#ffffff", "backgroundColor": "#149e60"},  # dark green
    # Legal & Government
    "Legal & Government/Legal":          {"textColor": "#ffffff", "backgroundColor": "#6d9eeb"},  # periwinkle
    "Legal & Government/Government":     {"textColor": "#ffffff", "backgroundColor": "#3c78d8"},  # dark blue
    "Legal & Government/Politics":       {"textColor": "#ffffff", "backgroundColor": "#285bac"},  # navy
    # Shopping
    "Shopping/Product Purchases":        {"textColor": "#ffffff", "backgroundColor": "#eba093"},  # salmon
    "Shopping/Product Downloads":        {"textColor": "#ffffff", "backgroundColor": "#c9daf8"},  # light blue
    "Shopping/Licenses and Keys":        {"textColor": "#ffffff", "backgroundColor": "#a46a21"},  # brown
    "Shopping/Shipping and Delivery":    {"textColor": "#ffffff", "backgroundColor": "#fbc8d9"},  # blush
    # Security
    "Security/Account Security":         {"textColor": "#ffffff", "backgroundColor": "#cc3a21"},  # dark red
    "Security/Logins and Verification":  {"textColor": "#ffffff", "backgroundColor": "#ac2b16"},  # deep red
    # Health & Travel
    "Health & Travel/Health and Insurance": {"textColor": "#ffffff", "backgroundColor": "#b9e4d0"},  # light green
    "Health & Travel/Travel":            {"textColor": "#ffffff", "backgroundColor": "#ffd6a2"},  # peach
    # Personal
    "Personal/Personal":                 {"textColor": "#ffffff", "backgroundColor": "#3dc789"},  # teal
    "Personal/Education":                {"textColor": "#ffffff", "backgroundColor": "#b694e8"},  # lavender
    "Personal/Employment":               {"textColor": "#ffffff", "backgroundColor": "#a4c2f4"},  # sky blue
}

CLASSIFICATION_SYSTEM_PROMPT = """You are an email triage assistant. Your job is to classify emails into categories so the user's inbox stays clean and organized.

OWNER: {owner_name}
OWNER'S EMAIL ACCOUNTS: {account_emails}

## BUSINESS ENTITY categories (the owner's businesses — each gets its own label):
- Audio Services: Daniel's freelance audio engineering, recording, mixing, mastering, and production work for external clients (NOT Terra Cognita band work)
- Terra Cognita: Everything related to Daniel's band Terra Cognita — gigs, shows, rehearsals, band member communications, booking inquiries, setlists, merch, social media for the band. Email account: terracognitamusic@gmail.com
- Well Made Plays: Music management and events company co-run with Douglas Schmidt (Doug Schmidt). Bookings, venue deals, artist management, event logistics, revenue splits, contracts
- The Chorus Crafters: Custom song company — commissions, client orders, song delivery, revisions, demos, deposits, payments for personalized songs (weddings, memorials, birthdays). Co-run with Dan Hochman. Email account: thechoruscrafters@gmail.com
- 4400 Mount Vernon Drive: Rental property (LLC) — tenants, rent, leases, maintenance, repairs, property tax, HOA, contractors, property management
- 2300 Southern Oaks: Daniel's primary residence (personal home, NOT a business/LLC) — pool service, pool maintenance, construction contractors, home renovation, home utilities (electric, water, gas, internet), home insurance, home warranty, landscaping, pest control, HVAC, plumbing, general home repair

## KEEP categories (important — label and keep):
- Personal: Friends, family, personal correspondence, personal plans
- Tax: Tax documents, W-2s, 1099s, tax prep, IRS, state tax agencies, CPA correspondence, estimated tax payments, tax refunds
- Fees and Bills: Subscription charges, utility bills, payment confirmations, bank fees, service charges, recurring charges, invoices you owe
- Government: DMV, city/county/state/federal agencies, voter registration, jury duty, census, government benefits, USPS, passport
- Politics: Genuine political correspondence — emails from elected officials or representatives you've contacted, policy updates from YOUR representatives, town hall invitations, constituent services, ballot/election info from official sources. NOT mass fundraising or campaign blasts
- Product Purchases: Order confirmations, purchase receipts, warranty info, product registrations, digital and physical purchases from stores
- Product Downloads: Software downloads, app purchase confirmations, digital product delivery, download links, installer access
- Licenses and Keys: Software license keys, product activation codes, serial numbers, registration codes, API keys, certificate files, digital entitlements, license renewal notices
- Banking and Investments: Banking, investment statements, credit card statements, loan documents, Fidelity, brokerage, 401k, financial advisors, Found banking
- Health and Insurance: Medical, dental, vision, prescriptions, insurance policies and claims, doctor correspondence, lab results, EOBs
- Travel: Flight confirmations, boarding passes, hotel reservations, Airbnb, car rental confirmations, trip itineraries, travel insurance, TSA, airline communications, rental car receipts
- Legal: Contracts, legal notices, attorney correspondence, lawsuits, legal agreements, terms changes from important services
- Education: Courses, certifications, training, academic correspondence, online learning platforms
- Employment: Job-related (when Daniel is the employee), HR, payroll, benefits enrollment
- Shipping and Delivery: Package tracking, delivery notifications, shipping confirmations, carrier updates (UPS, FedEx, USPS, Amazon delivery)
- Account Security: Password resets, two-factor authentication codes, security alerts, breach notifications, recovery codes, backup codes
- Logins and Verification: Email verification, account verification, new device sign-ins, login confirmations, identity verification, "confirm your email" messages

## JUNK category (auto-deleted, no label):
- Junk: ALL of the following get auto-deleted with NO label — marketing emails, sales pitches, promotional offers, discount codes, newsletters, blog digests, content roundups, coupons, store announcements, spam, scams, phishing, social media notifications (LinkedIn, Facebook, Instagram likes/follows/comments), forum digests, non-critical automated alerts (CI/CD, monitoring, onboarding drip campaigns, "welcome to X"), mass campaign fundraising blasts, PAC solicitations, political auto-mailers ("chip in $5", bulk unsubscribe footers), Glassdoor job alerts, and any other bulk/auto-generated email with no personal or business value

## IMPORTANT: There is NO "Important" catch-all category. Every email MUST be classified into one of the specific categories above. If an email is genuinely important but doesn't fit any category, pick the CLOSEST match (e.g., a miscellaneous business email → the relevant business entity or "Personal").

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
- action: "label" (keep in inbox with category label) or "archive" (label + remove from inbox). Emails classified as "Junk" are auto-deleted regardless of action.
- confidence: "high", "medium", or "low"

Guidelines for action:
- "label": Emails the user should see or may need to act on — business, financial, security, travel, licenses, personal
- "archive": Emails worth keeping for records but not needing inbox attention (old receipts, past notifications, etc.)
- Any email categorized as "Junk" will be auto-deleted — no label, straight to trash

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

            # Junk → auto-delete, no label
            is_junk = category in JUNK_CATEGORIES

            # Safety: never trash with low confidence
            if is_junk and confidence == "low":
                action = "archive"  # demote to archive instead of delete

            if dry_run:
                subj = email_map.get(email_id, {}).get("subject", "?")
                fate = "DELETE" if is_junk else action
                log.info(f"[DRY RUN] {email_id}: {category} → {fate} ({confidence}) — {subj}")
                stats["trashed" if is_junk else "labeled"] += 1
                continue

            try:
                if is_junk:
                    # Trash directly — no label
                    gmail_client.trash_email(email_id)
                    stats["trashed"] += 1
                else:
                    # Apply colored category label (nested path)
                    label_name = self._label_name_for_category(category)
                    color = LABEL_COLORS.get(label_name)
                    label_id = gmail_client.get_or_create_label(label_name, color=color)

                    if action == "archive":
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
        """Map a classifier category to a nested Gmail label path.

        e.g. "Terra Cognita" → "Business/Terra Cognita"
             "Tax" → "Finance/Tax"
        """
        return LABEL_PATH_MAP.get(category, f"Personal/{category}")

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
