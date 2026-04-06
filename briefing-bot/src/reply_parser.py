"""
Digest reply parser — scans for replies to digest emails and marks items done.

When the user replies to a digest email with commands like:
    done A3
    done A3 D5 T2
    done A3, done D5

This module parses those replies and updates the database accordingly.

Reference code format:
    A = action_items, D = deadlines, M = financial_items,
    T = tasks, F = follow_ups, G = agreements
"""
import logging
import re
from datetime import datetime, timedelta

from . import database as db
from .gmail_client import GmailClient

log = logging.getLogger(__name__)

# Map single-letter prefix → (table_name, done_status)
REF_MAP = {
    "A": ("action_items", "done"),
    "D": ("deadlines", "done"),
    "M": ("financial_items", "resolved"),
    "T": ("tasks", "done"),
    "F": ("follow_ups", "dismissed"),
    "G": ("agreements", "fulfilled"),
}

# Matches codes like A3, D15, T2 — case insensitive
CODE_PATTERN = re.compile(r"\b([ADMTFG])(\d+)\b", re.IGNORECASE)


def parse_reply_text(text: str) -> list[tuple[str, int]]:
    """Extract reference codes from a reply body.

    Accepts formats like:
        done A3
        done A3 D5 T2
        done A3, done D5
        A3 D5 (bare codes also accepted)

    Returns list of (prefix_letter, item_id) tuples.
    """
    # Normalize to uppercase
    text = text.upper()

    # Find all reference codes that appear after "done" or standalone
    codes = CODE_PATTERN.findall(text)
    return [(prefix, int(item_id)) for prefix, item_id in codes]


def process_digest_replies(gmail: GmailClient, owner_email: str) -> int:
    """Scan for replies to digest emails and process 'done' commands.

    Returns the number of items marked done.
    """
    if not gmail.service:
        gmail.authenticate()

    # Search for replies to digest emails from the owner, in the last 7 days
    since = datetime.utcnow() - timedelta(days=7)
    query = (
        f"from:{owner_email} "
        f"subject:(Re: Briefing) "
        f"after:{since.strftime('%Y/%m/%d')} "
        f"in:sent"
    )

    results = gmail.service.users().messages().list(
        userId="me", q=query, maxResults=20
    ).execute()

    replies = results.get("messages", [])
    if not replies:
        return 0

    # Track which replies we've already processed (stored in sync_state)
    processed_ids = set()
    raw = db.get_sync_state("processed_digest_replies")
    if raw:
        processed_ids = set(raw.split(","))

    total_marked = 0
    newly_processed = []

    for msg_ref in replies:
        msg_id = msg_ref["id"]
        if msg_id in processed_ids:
            continue

        # Fetch the full message to get the reply body
        msg = gmail.service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        body = gmail._extract_body(msg.get("payload", {}))
        if not body:
            body = msg.get("snippet", "")

        codes = parse_reply_text(body)
        if not codes:
            newly_processed.append(msg_id)
            continue

        for prefix, item_id in codes:
            prefix = prefix.upper()
            if prefix not in REF_MAP:
                continue
            table, done_status = REF_MAP[prefix]
            try:
                db.update_item_status(table, item_id, done_status)
                log.info(f"Marked {prefix}{item_id} ({table} #{item_id}) as {done_status}")
                total_marked += 1
            except Exception as e:
                log.warning(f"Failed to mark {prefix}{item_id}: {e}")

        newly_processed.append(msg_id)

    # Save processed reply IDs
    if newly_processed:
        all_processed = processed_ids | set(newly_processed)
        # Keep only last 200 IDs to avoid unbounded growth
        trimmed = sorted(all_processed)[-200:]
        db.set_sync_state("processed_digest_replies", ",".join(trimmed))

    if total_marked:
        log.info(f"Processed {total_marked} item(s) from digest replies")

    return total_marked
