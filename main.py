#!/usr/bin/env python3
"""
Personal Communication Tracker — CLI entry point.

Usage:
    python main.py setup          # Initialize DB, authenticate Gmail
    python main.py fetch          # Fetch new emails from Gmail
    python main.py analyze        # Analyze unprocessed emails with Claude
    python main.py digest         # Generate and send today's briefing
    python main.py run            # Fetch + analyze + digest in one shot
    python main.py status         # Show dashboard summary
    python main.py schedule       # Run on recurring schedule (daemon mode)
    python main.py mark <table> <id> <status>  # Update item status

    # Chorus Crafters order tracking
    python main.py orders list              # Show active order pipeline
    python main.py orders list --all        # Include completed/cancelled
    python main.py orders view <id>         # Full order detail
    python main.py orders add               # Manually create an order
    python main.py orders update <id>       # Update order fields
    python main.py orders pipeline          # Revenue pipeline summary
"""
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from src.entities import load_config, load_entities
from datetime import date as date_type

from src.database import (
    init_db,
    store_email,
    store_extractions,
    get_unprocessed_emails,
    get_dashboard_summary,
    get_pending_deadlines,
    get_pending_financial,
    get_active_agreements,
    get_pending_actions,
    get_sync_state,
    set_sync_state,
    update_item_status,
    mark_email_processed,
    # order tracking
    upsert_song_order,
    update_order,
    get_order,
    get_all_orders,
    get_orders_by_status,
    get_orders_pipeline_summary,
    # calendar
    store_calendar_events,
    get_upcoming_events,
    # tasks
    add_task,
    get_pending_tasks,
    complete_task,
    delete_task,
    # follow-ups
    upsert_follow_up,
    get_pending_follow_ups,
    dismiss_follow_up,
    mark_follow_up_replied,
    get_stale_action_items,
    # labeling
    get_unlabeled_emails,
    mark_emails_labeled,
    # horizon
    get_horizon_data,
    # snooze
    snooze_item,
    unsnooze_item,
    get_snoozed_items,
    SNOOZEABLE_TABLES,
    # organizer
    is_email_organized,
    store_organized_email,
    get_organized_summary,
)
from src.gmail_client import GmailClient, build_clients, get_send_client
from src.organizer import EmailOrganizer
from src.calendar_client import CalendarClient
from src.analyzer import Analyzer
from src.digest import DigestGenerator
from src.scheduler import TrackerScheduler
from src.orders import (
    STATUS_LABELS,
    STATUS_ORDER,
    EVENT_TYPE_LABELS,
    format_order_row,
    format_order_detail,
)

load_dotenv()
console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("tracker")


SMS_FORWARD_INDICATORS = [
    "fwd: text from", "forwarded text", "sms from", "text message from",
    "message from +1", "new text from",
]


def get_config():
    config_path = Path("config.yaml")
    if not config_path.exists():
        console.print("[red]config.yaml not found.[/red]")
        sys.exit(1)
    return load_config(str(config_path))


def _is_sms_forward(email: dict, config: dict) -> bool:
    """Detect if an email is a forwarded SMS."""
    subject = (email.get("subject") or "").lower()
    prefix = config.get("sms", {}).get(
        "forwarding_email_subject_prefix", "fwd: text from"
    ).lower()
    return subject.startswith(prefix) or any(
        ind in subject for ind in SMS_FORWARD_INDICATORS
    )


def do_fetch(config):
    """Fetch new emails from all configured Gmail accounts."""
    entities = load_entities(config)
    google_cfg = config.get("google", {})
    max_emails = google_cfg.get("max_emails_per_fetch", 100)

    # Determine lookback window
    last_fetch = get_sync_state("last_email_fetch")
    if last_fetch:
        since = datetime.fromisoformat(last_fetch) - timedelta(hours=1)
    else:
        lookback = google_cfg.get("lookback_days", 30)
        since = datetime.now() - timedelta(days=lookback)

    clients = build_clients(config)
    total_stored = 0

    for client in clients:
        console.print(f"  Fetching {client.account_email} since {since.strftime('%Y-%m-%d')}...")
        try:
            client.authenticate()
            emails = client.fetch_emails(since=since, max_results=max_emails)
        except Exception as e:
            log.error(f"  Failed to fetch {client.account_email}: {e}")
            continue

        console.print(f"    Found {len(emails)} emails")
        stored = 0
        for email in emails:
            # Detect SMS forwards
            email["is_sms_forward"] = _is_sms_forward(email, config)

            # Keyword-based entity hint using account's primary entities + content
            combined = f"{email.get('subject', '')} {email.get('body_snippet', '')}"
            entity_key = None

            # First check account-level hints from config
            account_cfg = next(
                (a for a in config.get("accounts", []) if a["email"] == client.account_email),
                {}
            )
            primary = account_cfg.get("primary_entities", [])

            # Try keyword match within primary entities first, then all
            candidates = [
                (k, entities[k]) for k in primary if k in entities
            ] + [
                (k, v) for k, v in entities.items() if k not in primary
            ]
            for key, entity in candidates:
                if entity.matches_text(combined):
                    entity_key = key
                    break

            email["entity_key"] = entity_key
            store_email(email)
            stored += 1
            total_stored += 1

        console.print(f"    Stored {stored}")

    set_sync_state("last_email_fetch", datetime.now().isoformat())
    console.print(f"[green]Total emails stored: {total_stored}[/green]")
    return total_stored


def do_fetch_calendar(config):
    """Fetch upcoming calendar events from all accounts."""
    google_cfg = config.get("google", {})
    days_ahead = google_cfg.get("calendar_days_ahead", 30)
    clients = build_clients(config)
    total = 0

    for client in clients:
        console.print(f"  Calendar: {client.account_email}...")
        try:
            client.authenticate()
            cal = CalendarClient(client)
            events = cal.fetch_upcoming_events(days_ahead=days_ahead)
            store_calendar_events(events)
            console.print(f"    {len(events)} events")
            total += len(events)
        except Exception as e:
            log.error(f"  Calendar fetch failed for {client.account_email}: {e}")

    return total


def do_detect_follow_ups(config):
    """Scan each account's Sent folder and flag threads with no reply."""
    if not config.get("features", {}).get("follow_up_detection", True):
        return
    follow_up_days = config.get("features", {}).get("follow_up_days", 3)
    entities = load_entities(config)
    clients = build_clients(config)
    now_utc = datetime.now(timezone.utc)
    since = now_utc - timedelta(days=follow_up_days * 5)
    cutoff = now_utc - timedelta(days=follow_up_days)
    found = 0

    for client in clients:
        try:
            client.authenticate()
            sent = client.fetch_sent_emails(since=since, max_results=40)
        except Exception as e:
            log.error(f"  Sent fetch failed for {client.account_email}: {e}")
            continue

        # Keep only the most-recently-sent message per thread
        threads: dict[str, dict] = {}
        for email in sent:
            tid = email.get("thread_id")
            if not tid:
                continue
            if tid not in threads or email["date"] > threads[tid]["date"]:
                threads[tid] = email

        for thread_id, last_sent in threads.items():
            try:
                sent_dt = datetime.fromisoformat(last_sent["date"])
                # Ensure timezone-aware for comparison
                if sent_dt.tzinfo is None:
                    sent_dt = sent_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if sent_dt > cutoff:
                continue  # too recent to flag

            # Check if anyone replied after our sent date
            try:
                thread_msgs = client.get_thread_messages(thread_id)
            except Exception:
                continue

            thread_msgs.sort(key=lambda m: m.get("date", ""))
            has_reply = any(
                m["date"] > last_sent["date"]
                and client.account_email.lower() not in m.get("sender", "").lower()
                for m in thread_msgs
            )
            if has_reply:
                mark_follow_up_replied(thread_id)
                continue

            # Determine entity from subject
            entity_key = None
            subj = last_sent.get("subject", "")
            for key, entity in entities.items():
                if entity.matches_text(subj):
                    entity_key = key
                    break

            days_waiting = (now_utc - sent_dt).days
            recipient = last_sent.get("to", "").split(",")[0].strip()
            upsert_follow_up({
                "thread_id": thread_id,
                "account_email": client.account_email,
                "subject": last_sent.get("subject", "(no subject)"),
                "recipient": recipient,
                "last_sent_date": sent_dt.date().isoformat(),
                "entity_key": entity_key,
                "days_waiting": days_waiting,
            })
            found += 1

    console.print(f"[green]Follow-up detection: {found} thread(s) awaiting reply[/green]")


def do_apply_labels(config):
    """Apply Gmail entity labels to classified emails (requires gmail.modify scope)."""
    if not config.get("features", {}).get("auto_label_emails", True):
        return
    entities = load_entities(config)
    entity_label_map = {
        key: f"Tracker/{entity.name}"
        for key, entity in entities.items()
    }
    unlabeled = get_unlabeled_emails(limit=200)
    if not unlabeled:
        return

    # Group by account_email
    by_account: dict[str, list[dict]] = {}
    for email in unlabeled:
        acct = email.get("account_email", "")
        by_account.setdefault(acct, []).append(email)

    clients = build_clients(config)
    client_map = {c.account_email: c for c in clients}
    labeled_ids = []

    for account_email, emails in by_account.items():
        client = client_map.get(account_email)
        if not client:
            continue
        try:
            client.authenticate()
        except Exception as e:
            log.error(f"  Label auth failed for {account_email}: {e}")
            continue

        for email in emails:
            entity_key = email.get("entity_key")
            label_name = entity_label_map.get(entity_key)
            if not label_name:
                labeled_ids.append(email["id"])  # mark as done even if no label
                continue
            try:
                label_id = client.get_or_create_label(label_name)
                client.apply_label(email["id"], label_id)
                labeled_ids.append(email["id"])
            except Exception as e:
                log.warning(f"  Label failed for {email['id']}: {e}")

    if labeled_ids:
        mark_emails_labeled(labeled_ids)
        console.print(f"[green]Auto-labeled {len(labeled_ids)} email(s) in Gmail[/green]")


def do_analyze(config):
    """Analyze unprocessed emails using Claude."""
    entities = load_entities(config)
    analysis_cfg = config.get("analysis", {})
    model = analysis_cfg.get("model", "claude-opus-4-6")
    batch_size = analysis_cfg.get("batch_size", 20)

    analyzer = Analyzer(entities, model=model)
    unprocessed = get_unprocessed_emails(limit=batch_size * 5)

    if not unprocessed:
        console.print("No unprocessed emails to analyze.")
        return 0

    console.print(f"Analyzing {len(unprocessed)} emails in batches of {batch_size}...")
    total_items = 0

    for i in range(0, len(unprocessed), batch_size):
        batch = unprocessed[i : i + batch_size]
        console.print(f"  Processing batch {i // batch_size + 1} ({len(batch)} emails)...")

        try:
            results = analyzer.analyze_batch(batch)
        except Exception as e:
            log.error(f"Analysis failed for batch: {e}")
            continue

        for email in batch:
            email_id = email["id"]
            if email_id in results:
                extractions = results[email_id]

                # Update entity classification from Claude's analysis
                if extractions.get("entity_key"):
                    from src.database import get_connection

                    conn = get_connection()
                    conn.execute(
                        "UPDATE emails SET entity_key = ? WHERE id = ?",
                        (extractions["entity_key"], email_id),
                    )
                    conn.commit()
                    conn.close()

                store_extractions(email_id, extractions)
                n = (
                    len(extractions.get("agreements", []))
                    + len(extractions.get("deadlines", []))
                    + len(extractions.get("financial_items", []))
                    + len(extractions.get("action_items", []))
                )
                total_items += n
            else:
                mark_email_processed(email_id)

    console.print(f"[green]Extracted {total_items} items from {len(unprocessed)} emails[/green]")
    return total_items


def do_digest(config, digest_type="daily"):
    """Generate and send the digest email."""
    entities = load_entities(config)
    analysis_cfg = config.get("analysis", {})
    model = analysis_cfg.get("model", "claude-opus-4-6")
    send_to = config.get("digest", {}).get("send_to", "")

    if not send_to:
        console.print("[red]No digest.send_to configured in config.yaml[/red]")
        return

    # Use the designated send-from account
    clients = build_clients(config)
    send_client = get_send_client(config, clients)
    send_client.authenticate()

    analyzer = Analyzer(entities, model=model)
    generator = DigestGenerator(analyzer, send_client, entities, send_to)
    html = generator.generate_and_send(digest_type)
    console.print(f"[green]Digest sent to {send_to}[/green]")
    return html


# ── CLI ──────────────────────────────────────────────────────────────

@click.group()
def cli():
    """Personal Communication Tracker — your AI-powered business assistant."""
    pass


@cli.command()
def setup():
    """Initialize the database. Run setup-accounts to authenticate Gmail."""
    init_db()
    console.print("[green]Database initialized.[/green]")
    console.print("Next: run [bold]python main.py setup-accounts[/bold] to authorize your Gmail accounts.")


@cli.command(name="setup-accounts")
def setup_accounts():
    """Authenticate each configured Gmail account (opens browser once per account)."""
    config = get_config()
    init_db()
    clients = build_clients(config)
    accounts = config.get("accounts", [])

    console.print(f"[bold]Authorizing {len(clients)} Gmail account(s)...[/bold]\n")
    for i, (client, acct_cfg) in enumerate(zip(clients, accounts)):
        console.print(f"[{i+1}/{len(clients)}] {acct_cfg['name']} ({client.account_email})")
        try:
            client.authenticate()
            console.print(f"  [green]✓ Authorized[/green]\n")
        except FileNotFoundError as e:
            console.print(f"  [red]{e}[/red]\n")

    console.print("[bold]Also enable the Google Calendar API:[/bold]")
    console.print("  console.cloud.google.com → APIs & Services → Library → Calendar API → Enable\n")
    console.print("[green]Done! Run [bold]python main.py run[/bold] to fetch emails and calendar.[/green]")


@cli.command()
def fetch():
    """Fetch new emails from all Gmail accounts."""
    config = get_config()
    init_db()
    console.print("[bold]Fetching emails...[/bold]")
    do_fetch(config)
    console.print("[bold]Fetching calendar events...[/bold]")
    do_fetch_calendar(config)


@cli.command()
def analyze():
    """Analyze unprocessed emails with Claude."""
    config = get_config()
    init_db()
    do_analyze(config)
    console.print("[bold]Applying Gmail labels...[/bold]")
    do_apply_labels(config)


@cli.command()
@click.option("--type", "digest_type", default="daily", type=click.Choice(["daily", "weekly"]))
def digest(digest_type):
    """Generate and send a briefing email."""
    config = get_config()
    init_db()
    do_digest(config, digest_type)


@cli.command()
def run():
    """Fetch emails + calendar, analyze, organize, and send digest in one shot."""
    config = get_config()
    init_db()
    console.print("[bold]Fetching emails from all accounts...[/bold]")
    do_fetch(config)
    console.print("[bold]Fetching calendar events...[/bold]")
    do_fetch_calendar(config)
    console.print("[bold]Analyzing with Claude...[/bold]")
    do_analyze(config)
    console.print("[bold]Applying Gmail labels...[/bold]")
    do_apply_labels(config)
    console.print("[bold]Organizing inbox...[/bold]")
    _do_organize(config)
    console.print("[bold]Detecting follow-ups needed...[/bold]")
    do_detect_follow_ups(config)
    console.print("[bold]Sending digest...[/bold]")
    do_digest(config)


@cli.command()
def status():
    """Show dashboard summary."""
    init_db()
    summary = get_dashboard_summary()

    table = Table(title="Communication Tracker Status")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total Emails Tracked", str(summary["total_emails"]))
    table.add_row("Unprocessed Emails", str(summary["unprocessed_emails"]))
    table.add_row("Calendar Events (7 days)", str(summary["upcoming_events_7d"]))
    table.add_row("Active Agreements", str(summary["active_agreements"]))
    table.add_row("Pending Deadlines", str(summary["pending_deadlines"]))
    table.add_row("Money Owed to You", f"${summary['money_owed_to_you']:,.2f}")
    table.add_row("Money You Owe", f"${summary['money_you_owe']:,.2f}")
    table.add_row("Pending Action Items", str(summary["pending_actions"]))
    table.add_row("Stale Actions (3+ days)", str(summary.get("stale_actions", 0)))
    table.add_row("Tasks (floating)", str(summary.get("pending_tasks", 0)))
    table.add_row("Awaiting Reply", str(summary.get("follow_ups_waiting", 0)))
    table.add_section()
    table.add_row("Active Song Orders (CC)", str(summary["active_song_orders"]))
    table.add_row("Song Orders Pipeline Value", f"${summary['song_orders_pipeline_value']:,.2f}")
    console.print(table)

    # Show upcoming calendar events
    events = get_upcoming_events(days_ahead=7)
    if events:
        console.print("\n[bold]Calendar — Next 7 Days:[/bold]")
        for ev in events:
            when = ev.get("start_datetime") or ev.get("start_date") or "?"
            when = when[:10]  # date portion only
            cal = ev.get("calendar_name", "")
            console.print(f"  {when}  {ev['title']}  [dim]({cal})[/dim]")

    # Show upcoming deadlines
    deadlines = get_pending_deadlines(days_ahead=7)
    if deadlines:
        console.print("\n[bold]Upcoming Deadlines (7 days):[/bold]")
        for d in deadlines:
            entity = d.get("entity_key", "personal") or "personal"
            console.print(f"  [{d.get('priority', 'medium')}] {d['description']} — due {d.get('due_date', '?')} ({entity})")

    # Show money owed to you
    receivables = get_pending_financial(direction="receivable")
    if receivables:
        console.print("\n[bold]Money Owed to You:[/bold]")
        for r in receivables:
            amt = f"${r['amount']:,.2f}" if r.get("amount") else "amount TBD"
            entity = r.get("entity_key", "personal") or "personal"
            console.print(f"  {r.get('counterparty', '?')} — {amt} for {r.get('description', '?')} ({entity})")

    # Show pending actions
    actions = get_pending_actions()
    if actions:
        console.print("\n[bold]Action Items:[/bold]")
        for a in actions[:10]:
            entity = a.get("entity_key", "personal") or "personal"
            console.print(f"  [{a.get('priority', 'medium')}] {a['description']} ({entity})")

    # Show floating tasks
    tasks = get_pending_tasks()
    if tasks:
        console.print("\n[bold]Your Task List:[/bold]")
        for t in tasks:
            due = f" — due {t['due_date']}" if t.get("due_date") else ""
            entity = t.get("entity_key", "personal") or "personal"
            console.print(f"  #{t['id']} [{t.get('priority','medium')}] {t['title']}{due} ({entity})")

    # Show follow-ups
    followups = get_pending_follow_ups()
    if followups:
        console.print("\n[bold]Awaiting Reply:[/bold]")
        for f in followups:
            console.print(f"  #{f['id']} {f['subject']} → {f.get('recipient','?')} "
                          f"[dim]({f['days_waiting']}d waiting)[/dim]")


@cli.command()
@click.argument("table", type=click.Choice(["agreements", "deadlines", "financial_items", "action_items"]))
@click.argument("item_id", type=int)
@click.argument("new_status")
def mark(table, item_id, new_status):
    """Update an item's status (e.g., mark a deadline as 'done')."""
    init_db()
    update_item_status(table, item_id, new_status)
    console.print(f"[green]Updated {table} #{item_id} → {new_status}[/green]")


@cli.command(name="schedule")
def schedule_cmd():
    """Run the tracker on a recurring schedule (daemon mode)."""
    config = get_config()
    init_db()

    def _full_fetch():
        do_fetch(config)
        do_fetch_calendar(config)
        do_apply_labels(config)
        _do_organize(config)
        do_detect_follow_ups(config)

    scheduler = TrackerScheduler(
        fetch_fn=_full_fetch,
        analyze_fn=lambda: do_analyze(config),
        digest_fn=lambda dt: do_digest(config, dt),
        config=config,
    )

    console.print("[bold]Starting scheduled tracker...[/bold]")
    console.print("Running initial fetch + analyze cycle...")
    do_fetch(config)
    do_fetch_calendar(config)
    do_analyze(config)
    console.print("[green]Initial cycle complete. Entering schedule loop.[/green]")
    scheduler.run_forever()


# ── Chorus Crafters Order Tracking ───────────────────────────────────────────

@cli.group()
def orders():
    """Chorus Crafters custom song order pipeline."""
    pass


@orders.command(name="list")
@click.option("--all", "show_all", is_flag=True, help="Include completed and cancelled orders")
@click.option("--status", "filter_status", default=None, help="Filter by status")
def orders_list(show_all, filter_status):
    """Show the order pipeline."""
    init_db()

    if filter_status:
        rows = get_orders_by_status(filter_status)
    else:
        rows = get_all_orders(include_closed=show_all)

    if not rows:
        console.print("No orders found.")
        return

    table = Table(title="Chorus Crafters — Song Order Pipeline")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Client")
    table.add_column("Event")
    table.add_column("Event Date")
    table.add_column("Status")
    table.add_column("Price", justify="right")
    table.add_column("Dep.", justify="center")
    table.add_column("Revs", justify="center")

    for order in rows:
        table.add_row(*format_order_row(order))

    console.print(table)
    console.print(f"\n{len(rows)} order(s) shown. Use [bold]orders view <id>[/bold] for full detail.")


@orders.command(name="view")
@click.argument("order_id", type=int)
def orders_view(order_id):
    """Show full detail for a single order."""
    init_db()
    order = get_order(order_id)
    if not order:
        console.print(f"[red]Order #{order_id} not found.[/red]")
        return
    console.print(format_order_detail(order))


@orders.command(name="add")
def orders_add():
    """Manually create a new song order via interactive prompts."""
    init_db()
    console.print("[bold]New Chorus Crafters Order[/bold]")
    console.print("Press Enter to skip any field.\n")

    def ask(label, default=None):
        val = click.prompt(label, default=default or "", show_default=bool(default))
        return val.strip() or None

    def ask_float(label):
        val = click.prompt(label, default="", show_default=False)
        try:
            return float(val.strip())
        except (ValueError, AttributeError):
            return None

    def ask_int(label, default):
        val = click.prompt(label, default=str(default), show_default=True)
        try:
            return int(val.strip())
        except (ValueError, AttributeError):
            return default

    event_type = click.prompt(
        "Event type",
        type=click.Choice(["wedding", "memorial", "birthday", "anniversary", "other"]),
        default="wedding",
    )

    order = {
        "client_name": ask("Client name"),
        "client_email": ask("Client email"),
        "client_phone": ask("Client phone"),
        "event_type": event_type,
        "event_date": ask("Event date (YYYY-MM-DD)"),
        "honoree_names": ask("Honoree name(s)"),
        "event_notes": ask("Event notes (venue, context)"),
        "song_style": ask("Song style/vibe"),
        "song_story": ask("Story/details for the song"),
        "price": ask_float("Price ($)"),
        "deposit_amount": ask_float("Deposit amount ($)"),
        "revisions_included": ask_int("Revisions included", 2),
        "status": click.prompt(
            "Status",
            type=click.Choice(STATUS_ORDER),
            default="inquiry",
        ),
        "notes": ask("Notes"),
    }

    order_id = upsert_song_order(order)
    console.print(f"\n[green]Order #{order_id} created.[/green]")
    console.print(format_order_detail(get_order(order_id)))


@orders.command(name="update")
@click.argument("order_id", type=int)
@click.option("--status", default=None, type=click.Choice(STATUS_ORDER + ["cancelled"]))
@click.option("--deposit-paid", "deposit_paid", is_flag=True, default=None)
@click.option("--deposit-date", "deposit_date", default=None)
@click.option("--balance-paid", "balance_paid", is_flag=True, default=None)
@click.option("--balance-date", "balance_date", default=None)
@click.option("--demo-sent", "demo_delivered", is_flag=True, default=None)
@click.option("--demo-date", "demo_date", default=None)
@click.option("--final-sent", "final_delivered", is_flag=True, default=None)
@click.option("--final-date", "final_date", default=None)
@click.option("--revision-used", "add_revision", is_flag=True, help="Increment revisions_used by 1")
@click.option("--price", default=None, type=float)
@click.option("--notes", default=None)
@click.option("--event-date", "event_date", default=None)
def orders_update(order_id, status, deposit_paid, deposit_date, balance_paid,
                  balance_date, demo_delivered, demo_date, final_delivered,
                  final_date, add_revision, price, notes, event_date):
    """Update fields on an existing order."""
    init_db()
    order = get_order(order_id)
    if not order:
        console.print(f"[red]Order #{order_id} not found.[/red]")
        return

    fields = {}
    if status is not None:
        fields["status"] = status
    if deposit_paid:
        fields["deposit_paid"] = 1
        if not deposit_date:
            from datetime import date
            deposit_date = date.today().isoformat()
    if deposit_date:
        fields["deposit_date"] = deposit_date
    if balance_paid:
        fields["balance_paid"] = 1
        if not balance_date:
            from datetime import date
            balance_date = date.today().isoformat()
    if balance_date:
        fields["balance_date"] = balance_date
    if demo_delivered:
        fields["demo_delivered"] = 1
        if not demo_date:
            from datetime import date
            demo_date = date.today().isoformat()
    if demo_date:
        fields["demo_date"] = demo_date
    if final_delivered:
        fields["final_delivered"] = 1
        if not final_date:
            from datetime import date
            final_date = date.today().isoformat()
    if final_date:
        fields["final_date"] = final_date
    if add_revision:
        fields["revisions_used"] = (order.get("revisions_used") or 0) + 1
    if price is not None:
        fields["price"] = price
    if notes is not None:
        fields["notes"] = notes
    if event_date is not None:
        fields["event_date"] = event_date

    if not fields:
        console.print("[yellow]Nothing to update — provide at least one option.[/yellow]")
        return

    update_order(order_id, fields)
    console.print(f"[green]Order #{order_id} updated.[/green]")
    console.print(format_order_detail(get_order(order_id)))


@orders.command(name="pipeline")
def orders_pipeline():
    """Show Chorus Crafters revenue pipeline summary."""
    init_db()
    pipeline = get_orders_pipeline_summary()

    table = Table(title="Chorus Crafters — Revenue Pipeline")
    table.add_column("Status")
    table.add_column("Orders", justify="right")
    table.add_column("Total Value", justify="right")
    table.add_column("Deposits In", justify="right")
    table.add_column("Balances In", justify="right")

    total_orders = 0
    total_value = 0.0
    total_deps = 0.0
    total_bals = 0.0

    for status in STATUS_ORDER:
        if status not in pipeline:
            continue
        row = pipeline[status]
        label = STATUS_LABELS.get(status, status)
        table.add_row(
            label,
            str(row["count"]),
            f"${row['total_value']:,.2f}",
            f"${row['deposits_collected']:,.2f}",
            f"${row['balances_collected']:,.2f}",
        )
        total_orders += row["count"]
        total_value += row["total_value"]
        total_deps += row["deposits_collected"]
        total_bals += row["balances_collected"]

    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_orders}[/bold]",
        f"[bold]${total_value:,.2f}[/bold]",
        f"[bold]${total_deps:,.2f}[/bold]",
        f"[bold]${total_bals:,.2f}[/bold]",
    )

    console.print(table)
    collected = total_deps + total_bals
    outstanding = total_value - collected
    console.print(f"\nCollected: [green]${collected:,.2f}[/green]   "
                  f"Outstanding: [yellow]${outstanding:,.2f}[/yellow]")


# ── 14-Day Horizon ───────────────────────────────────────────────────────────

@cli.command()
@click.option("--days", default=14, help="How many days ahead to show")
def horizon(days):
    """Show upcoming calendar events cross-referenced with pending items."""
    init_db()
    data = get_horizon_data(days_ahead=days)
    events = data["events"]

    if not events:
        console.print(f"[dim]No calendar events in the next {days} days.[/dim]")
        return

    def _items_for_event(event: dict) -> dict:
        """Find pending items related to this event by entity and date proximity."""
        entity = event.get("entity_key")
        raw_date = event.get("start_date") or (event.get("start_datetime") or "")[:10]
        try:
            ev_date = date_type.fromisoformat(raw_date)
        except Exception:
            ev_date = None

        results = {"actions": [], "financial": [], "deadlines": [], "follow_ups": [], "tasks": []}

        for item in data["action_items"]:
            if entity and item.get("entity_key") == entity:
                results["actions"].append(item)
            elif ev_date and item.get("due_date"):
                try:
                    delta = abs((ev_date - date_type.fromisoformat(item["due_date"])).days)
                    if delta <= 5:
                        results["actions"].append(item)
                except Exception:
                    pass

        for item in data["financial_items"]:
            if entity and item.get("entity_key") == entity:
                results["financial"].append(item)

        for item in data["deadlines"]:
            if entity and item.get("entity_key") == entity:
                results["deadlines"].append(item)
            elif ev_date and item.get("due_date"):
                try:
                    delta = abs((ev_date - date_type.fromisoformat(item["due_date"])).days)
                    if delta <= 5:
                        results["deadlines"].append(item)
                except Exception:
                    pass

        for item in data["follow_ups"]:
            if entity and item.get("entity_key") == entity:
                results["follow_ups"].append(item)

        for item in data["tasks"]:
            if entity and item.get("entity_key") == entity:
                results["tasks"].append(item)
            elif ev_date and item.get("due_date"):
                try:
                    delta = abs((ev_date - date_type.fromisoformat(item["due_date"])).days)
                    if delta <= 7:
                        results["tasks"].append(item)
                except Exception:
                    pass

        return results

    console.print(f"\n[bold]14-Day Horizon — Next {days} Days[/bold]\n")

    today = date_type.today()
    seen_item_ids: dict[str, set] = {k: set() for k in ["actions", "financial", "deadlines", "follow_ups", "tasks"]}

    for event in events:
        raw_date = event.get("start_date") or (event.get("start_datetime") or "")[:10]
        try:
            ev_date = date_type.fromisoformat(raw_date)
            days_away = (ev_date - today).days
            when = f"{raw_date} ({'+' if days_away >= 0 else ''}{days_away}d)"
        except Exception:
            when = raw_date

        cal = event.get("calendar_name", "")
        entity = event.get("entity_key", "")
        entity_tag = f"[dim]{entity}[/dim]" if entity else ""
        console.print(f"[bold cyan]📅 {when}  {event['title']}[/bold cyan]  {entity_tag}  [dim]({cal})[/dim]")

        items = _items_for_event(event)
        has_any = any(v for v in items.values())

        for item in items["deadlines"]:
            if item["id"] in seen_item_ids["deadlines"]:
                continue
            seen_item_ids["deadlines"].add(item["id"])
            due = item.get("due_date", "?")
            pri = item.get("priority", "medium")
            pri_color = "red" if pri == "high" else "yellow"
            console.print(f"   ⏰ [{pri_color}]{item['description']}[/{pri_color}]  due {due}")

        for item in items["financial"]:
            if item["id"] in seen_item_ids["financial"]:
                continue
            seen_item_ids["financial"].add(item["id"])
            amt = f"${item['amount']:,.2f}" if item.get("amount") else "amount TBD"
            direction = "→ owed to you" if item["direction"] == "receivable" else "← you owe"
            console.print(f"   💰 {item.get('counterparty','?')} — {amt}  {direction}  [dim]{item.get('description','')}[/dim]")

        for item in items["actions"]:
            if item["id"] in seen_item_ids["actions"]:
                continue
            seen_item_ids["actions"].add(item["id"])
            due = f"  due {item['due_date']}" if item.get("due_date") else ""
            pri = item.get("priority", "medium")
            pri_color = "red" if pri == "high" else ""
            txt = f"[{pri_color}]{item['description']}[/{pri_color}]" if pri_color else item["description"]
            console.print(f"   ✅ {txt}{due}")

        for item in items["tasks"]:
            if item["id"] in seen_item_ids["tasks"]:
                continue
            seen_item_ids["tasks"].add(item["id"])
            due = f"  due {item['due_date']}" if item.get("due_date") else ""
            console.print(f"   📋 [bold]{item['title']}[/bold]{due}  [dim](task #{item['id']})[/dim]")

        for item in items["follow_ups"]:
            if item["id"] in seen_item_ids["follow_ups"]:
                continue
            seen_item_ids["follow_ups"].add(item["id"])
            console.print(f"   📬 No reply from {item.get('recipient','?')}  [dim]{item.get('subject','')}  ({item['days_waiting']}d waiting)[/dim]")

        if not has_any:
            console.print("   [dim]— nothing pending[/dim]")
        console.print()


# ── Floating Tasks ────────────────────────────────────────────────────────────

@cli.group()
def tasks():
    """Manage your floating task list (todos not tied to any email)."""
    pass


@tasks.command(name="add")
@click.argument("title")
@click.option("--notes", default=None)
@click.option("--entity", "entity_key", default="personal")
@click.option("--due", "due_date", default=None, help="Due date YYYY-MM-DD")
@click.option("--priority", default="medium", type=click.Choice(["high", "medium", "low"]))
def tasks_add(title, notes, entity_key, due_date, priority):
    """Add a new task. Example: tasks add \"File Q1 taxes\" --due 2026-04-15 --priority high"""
    init_db()
    task_id = add_task(title, notes=notes, entity_key=entity_key, due_date=due_date, priority=priority)
    console.print(f"[green]Task #{task_id} added: {title}[/green]")


@tasks.command(name="list")
def tasks_list():
    """List all pending tasks."""
    init_db()
    items = get_pending_tasks()
    if not items:
        console.print("No pending tasks.")
        return
    table = Table(title="Your Task List")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Priority")
    table.add_column("Title")
    table.add_column("Entity")
    table.add_column("Due Date")
    table.add_column("Notes")
    for t in items:
        priority_style = {"high": "red", "medium": "yellow", "low": "green"}.get(t["priority"], "")
        table.add_row(
            str(t["id"]),
            f"[{priority_style}]{t['priority']}[/{priority_style}]",
            t["title"],
            t.get("entity_key") or "personal",
            t.get("due_date") or "—",
            (t.get("notes") or "")[:50],
        )
    console.print(table)


@tasks.command(name="done")
@click.argument("task_id", type=int)
def tasks_done(task_id):
    """Mark a task as complete."""
    init_db()
    complete_task(task_id)
    console.print(f"[green]Task #{task_id} marked done.[/green]")


@tasks.command(name="delete")
@click.argument("task_id", type=int)
def tasks_delete(task_id):
    """Delete a task permanently."""
    init_db()
    delete_task(task_id)
    console.print(f"[green]Task #{task_id} deleted.[/green]")


# ── Follow-up Tracking ────────────────────────────────────────────────────────

@cli.group()
def followups():
    """View and manage emails awaiting a reply."""
    pass


@followups.command(name="list")
def followups_list():
    """Show all threads where you sent last and haven't heard back."""
    init_db()
    items = get_pending_follow_ups()
    if not items:
        console.print("No follow-ups waiting.")
        return
    table = Table(title="Awaiting Reply")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Subject")
    table.add_column("Sent To")
    table.add_column("Account")
    table.add_column("Last Sent")
    table.add_column("Waiting", justify="right")
    table.add_column("Entity")
    for f in items:
        days = f.get("days_waiting", 0)
        days_style = "red" if days >= 7 else "yellow" if days >= 3 else ""
        table.add_row(
            str(f["id"]),
            (f.get("subject") or "")[:45],
            (f.get("recipient") or "")[:30],
            f.get("account_email", ""),
            f.get("last_sent_date", ""),
            f"[{days_style}]{days}d[/{days_style}]" if days_style else f"{days}d",
            f.get("entity_key") or "personal",
        )
    console.print(table)


@followups.command(name="dismiss")
@click.argument("followup_id", type=int)
def followups_dismiss(followup_id):
    """Dismiss a follow-up (mark as not needed)."""
    init_db()
    dismiss_follow_up(followup_id)
    console.print(f"[green]Follow-up #{followup_id} dismissed.[/green]")


@followups.command(name="scan")
def followups_scan():
    """Manually trigger a follow-up scan of sent emails."""
    config = get_config()
    init_db()
    do_detect_follow_ups(config)


# ── Snooze ───────────────────────────────────────────────────────────────────

SNOOZE_TABLE_CHOICES = sorted(SNOOZEABLE_TABLES)


@cli.group()
def snooze():
    """Snooze items so they stop appearing until a future date."""
    pass


@snooze.command(name="item")
@click.argument("table", type=click.Choice(SNOOZE_TABLE_CHOICES))
@click.argument("item_id", type=int)
@click.argument("until")
def snooze_cmd(table, item_id, until):
    """Snooze an item until a date or duration.

    \b
    UNTIL can be:
      3d          — snooze for 3 days
      1w          — snooze for 1 week
      2026-05-01  — snooze until a specific date

    \b
    Examples:
      snooze item action_items 5 3d
      snooze item deadlines 2 1w
      snooze item tasks 1 2026-04-20
      snooze item follow_ups 3 5d
    """
    init_db()
    try:
        snooze_date = snooze_item(table, item_id, until)
        console.print(f"[green]{table} #{item_id} snoozed until {snooze_date}[/green]")
        console.print("[dim]It won't appear in status, horizon, or digests until then.[/dim]")
    except ValueError as e:
        console.print(f"[red]Invalid duration: {e}[/red]")
        console.print("Use format: 3d, 1w, or YYYY-MM-DD")


@snooze.command(name="wake")
@click.argument("table", type=click.Choice(SNOOZE_TABLE_CHOICES))
@click.argument("item_id", type=int)
def snooze_wake(table, item_id):
    """Wake a snoozed item immediately so it reappears."""
    init_db()
    unsnooze_item(table, item_id)
    console.print(f"[green]{table} #{item_id} is now active again.[/green]")


@snooze.command(name="list")
def snooze_list():
    """Show all currently snoozed items."""
    init_db()
    items = get_snoozed_items()
    if not items:
        console.print("Nothing is snoozed.")
        return

    table = Table(title="Snoozed Items")
    table.add_column("Table")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Item")
    table.add_column("Snoozed Until")
    table.add_column("State")

    for item in items:
        state = item["snooze_state"]
        state_fmt = f"[dim]expired — run 'wake' to restore[/dim]" if state == "expired" else "[yellow]sleeping[/yellow]"
        table.add_row(
            item["source_table"],
            str(item["id"]),
            (item.get("label") or "")[:50],
            item["snoozed_until"],
            state_fmt,
        )
    console.print(table)
    console.print("\n[dim]Use 'snooze wake <table> <id>' to wake an item early.[/dim]")


# ── Email Organizer ─────────────────────────────────────────────────────────

@cli.group()
def organize():
    """Email organizer — auto-label, archive junk, and keep inbox clean."""
    pass


@organize.command(name="inbox")
@click.option("--dry-run", is_flag=True, help="Classify only — don't modify Gmail")
@click.option("--limit", "max_emails", default=100, help="Max emails to process")
@click.option("--account", default=None, help="Process only this account email")
def organize_inbox(dry_run, max_emails, account):
    """Organize current inbox emails — classify, label, and archive junk."""
    config = get_config()
    init_db()
    _do_organize(config, dry_run=dry_run, max_emails=max_emails, account_filter=account)


@organize.command(name="history")
@click.option("--dry-run", is_flag=True, help="Classify only — don't modify Gmail")
@click.option("--batch-size", default=50, help="Emails per page")
@click.option("--max-pages", default=20, help="Max pages to process (0 = unlimited)")
@click.option("--account", default=None, help="Process only this account email")
def organize_history(dry_run, batch_size, max_pages, account):
    """Deep-clean historical inbox — pages through all inbox emails."""
    config = get_config()
    init_db()
    _do_organize_history(
        config, dry_run=dry_run, batch_size=batch_size,
        max_pages=max_pages, account_filter=account,
    )


@organize.command(name="stats")
def organize_stats():
    """Show organizer statistics — how many emails sorted by category."""
    init_db()
    summary = get_organized_summary()

    if summary["total"] == 0:
        console.print("No emails organized yet. Run [bold]python main.py organize inbox[/bold] to start.")
        return

    table = Table(title=f"Email Organizer Stats — {summary['total']} emails processed")
    table.add_column("Category", style="bold")
    table.add_column("Count", justify="right")
    for cat, cnt in sorted(summary["by_category"].items(), key=lambda x: -x[1]):
        table.add_row(cat, str(cnt))

    table.add_section()
    table.add_row("[bold]By Action[/bold]", "")
    for action, cnt in sorted(summary["by_action"].items(), key=lambda x: -x[1]):
        style = {"label": "green", "archive": "yellow", "trash": "red"}.get(action, "")
        table.add_row(f"  [{style}]{action}[/{style}]", str(cnt))

    console.print(table)


def _build_organizer(config) -> EmailOrganizer:
    owner_name = config.get("owner", {}).get("name", "User")
    account_emails = [a["email"] for a in config.get("accounts", [])]
    model = config.get("organizer", {}).get("model", "claude-sonnet-4-6")
    batch_size = config.get("organizer", {}).get("batch_size", 25)
    return EmailOrganizer(
        owner_name=owner_name,
        account_emails=account_emails,
        model=model,
        batch_size=batch_size,
    )


def _do_organize(config, dry_run=False, max_emails=100, account_filter=None):
    """Organize current inbox for all (or one) account(s)."""
    organizer = _build_organizer(config)
    clients = build_clients(config)

    for client in clients:
        if account_filter and client.account_email != account_filter:
            continue
        console.print(f"\n[bold]Organizing {client.account_email}...[/bold]")
        try:
            client.authenticate()
        except Exception as e:
            log.error(f"Auth failed for {client.account_email}: {e}")
            continue

        emails, _ = client.fetch_inbox_emails(max_results=max_emails)
        # Filter out already-organized emails
        new_emails = [e for e in emails if not is_email_organized(e["id"])]

        if not new_emails:
            console.print("  No new emails to organize.")
            continue

        console.print(f"  {len(new_emails)} email(s) to classify (of {len(emails)} in inbox)...")

        # Process in batches
        total_stats = {"labeled": 0, "archived": 0, "trashed": 0, "skipped": 0, "errors": 0}
        for i in range(0, len(new_emails), organizer.batch_size):
            batch = new_emails[i : i + organizer.batch_size]
            console.print(f"  Batch {i // organizer.batch_size + 1} ({len(batch)} emails)...")

            stats, classifications = organizer.classify_and_act(batch, client, dry_run=dry_run)

            for key in total_stats:
                total_stats[key] += stats[key]

            # Record in database
            if not dry_run:
                for email_id, result in classifications.items():
                    store_organized_email(
                        email_id=email_id,
                        account_email=client.account_email,
                        category=result.get("category", "Important"),
                        action=result.get("action", "label"),
                        confidence=result.get("confidence", "medium"),
                        reason=result.get("reason", ""),
                    )

        prefix = "[DRY RUN] " if dry_run else ""
        console.print(
            f"  [green]{prefix}Done: {total_stats['labeled']} labeled, "
            f"{total_stats['archived']} archived, {total_stats['trashed']} trashed, "
            f"{total_stats['errors']} errors[/green]"
        )


def _do_organize_history(config, dry_run=False, batch_size=50, max_pages=20, account_filter=None):
    """Page through the entire inbox history and organize everything."""
    organizer = _build_organizer(config)
    clients = build_clients(config)

    for client in clients:
        if account_filter and client.account_email != account_filter:
            continue
        console.print(f"\n[bold]Deep-cleaning {client.account_email}...[/bold]")
        try:
            client.authenticate()
        except Exception as e:
            log.error(f"Auth failed for {client.account_email}: {e}")
            continue

        page = 0
        page_token = None
        total_stats = {"labeled": 0, "archived": 0, "trashed": 0, "skipped": 0, "errors": 0}
        total_processed = 0

        while True:
            if max_pages > 0 and page >= max_pages:
                console.print(f"  Reached max pages ({max_pages}). Use --max-pages 0 for unlimited.")
                break

            console.print(f"  Page {page + 1}: fetching up to {batch_size} emails...")
            emails, next_token = client.fetch_inbox_emails(
                max_results=batch_size, page_token=page_token
            )

            if not emails:
                console.print("  No more emails.")
                break

            # Filter already-organized
            new_emails = [e for e in emails if not is_email_organized(e["id"])]
            if not new_emails:
                console.print(f"  All {len(emails)} emails already organized, skipping...")
                if next_token:
                    page_token = next_token
                    page += 1
                    continue
                else:
                    break

            console.print(f"  Classifying {len(new_emails)} new emails...")
            stats, classifications = organizer.classify_and_act(new_emails, client, dry_run=dry_run)

            for key in total_stats:
                total_stats[key] += stats[key]
            total_processed += len(new_emails)

            if not dry_run:
                for email_id, result in classifications.items():
                    store_organized_email(
                        email_id=email_id,
                        account_email=client.account_email,
                        category=result.get("category", "Important"),
                        action=result.get("action", "label"),
                        confidence=result.get("confidence", "medium"),
                        reason=result.get("reason", ""),
                    )

            console.print(
                f"  Page {page + 1}: +{stats['labeled']} labeled, "
                f"+{stats['archived']} archived, +{stats['trashed']} trashed"
            )

            if not next_token:
                break
            page_token = next_token
            page += 1

        prefix = "[DRY RUN] " if dry_run else ""
        console.print(
            f"\n  [green]{prefix}History cleanup complete for {client.account_email}:[/green]"
        )
        console.print(
            f"  Processed {total_processed} emails: "
            f"{total_stats['labeled']} labeled, {total_stats['archived']} archived, "
            f"{total_stats['trashed']} trashed, {total_stats['errors']} errors"
        )


if __name__ == "__main__":
    cli()
