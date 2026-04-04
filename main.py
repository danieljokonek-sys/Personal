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
from datetime import datetime, timedelta
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from src.entities import load_config, load_entities
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
)
from src.gmail_client import GmailClient
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


def get_config():
    config_path = Path("config.yaml")
    if not config_path.exists():
        console.print("[red]config.yaml not found. Copy config.yaml.example and edit it.[/red]")
        sys.exit(1)
    return load_config(str(config_path))


def get_gmail(config):
    gmail_cfg = config.get("gmail", {})
    return GmailClient(
        credentials_file=gmail_cfg.get("credentials_file", "credentials/credentials.json"),
        token_file=gmail_cfg.get("token_file", "credentials/token.json"),
    )


def do_fetch(config):
    """Fetch new emails from Gmail and store them."""
    gmail = get_gmail(config)
    gmail.authenticate()
    entities = load_entities(config)

    gmail_cfg = config.get("gmail", {})
    max_emails = gmail_cfg.get("max_emails_per_fetch", 100)

    # Determine start date
    last_fetch = get_sync_state("last_email_fetch")
    if last_fetch:
        since = datetime.fromisoformat(last_fetch) - timedelta(hours=1)
    else:
        lookback = gmail_cfg.get("lookback_days", 7)
        since = datetime.now() - timedelta(days=lookback)

    console.print(f"Fetching emails since {since.strftime('%Y-%m-%d %H:%M')}...")
    emails = gmail.fetch_emails(since=since, max_results=max_emails)
    console.print(f"Found {len(emails)} emails")

    stored = 0
    for email in emails:
        # Quick entity classification by keywords
        combined_text = f"{email.get('subject', '')} {email.get('body_snippet', '')}"
        entity_key = None
        for key, entity in entities.items():
            if entity.matches_text(combined_text):
                entity_key = key
                break
        email["entity_key"] = entity_key
        store_email(email)
        stored += 1

    set_sync_state("last_email_fetch", datetime.now().isoformat())
    console.print(f"[green]Stored {stored} emails[/green]")
    return stored


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
    digest_cfg = config.get("digest", {})
    send_to = digest_cfg.get("send_to", config.get("owner", {}).get("email", ""))

    if not send_to:
        console.print("[red]No digest recipient configured in config.yaml[/red]")
        return

    gmail = get_gmail(config)
    gmail.authenticate()
    analyzer = Analyzer(entities, model=model)

    generator = DigestGenerator(analyzer, gmail, entities, send_to)
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
    """Initialize the database and authenticate with Gmail."""
    init_db()
    console.print("[green]Database initialized.[/green]")

    config = get_config()
    gmail = get_gmail(config)
    try:
        gmail.authenticate()
        console.print("[green]Gmail authenticated successfully.[/green]")
    except FileNotFoundError as e:
        console.print(f"[yellow]{e}[/yellow]")
        console.print("You can still use the tool — Gmail auth will be needed for fetch/digest.")


@cli.command()
def fetch():
    """Fetch new emails from Gmail."""
    config = get_config()
    init_db()
    do_fetch(config)


@cli.command()
def analyze():
    """Analyze unprocessed emails with Claude."""
    config = get_config()
    init_db()
    do_analyze(config)


@cli.command()
@click.option("--type", "digest_type", default="daily", type=click.Choice(["daily", "weekly"]))
def digest(digest_type):
    """Generate and send a briefing email."""
    config = get_config()
    init_db()
    do_digest(config, digest_type)


@cli.command()
def run():
    """Fetch, analyze, and send digest in one shot."""
    config = get_config()
    init_db()
    do_fetch(config)
    do_analyze(config)
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
    table.add_row("Active Agreements", str(summary["active_agreements"]))
    table.add_row("Pending Deadlines", str(summary["pending_deadlines"]))
    table.add_row("Money Owed to You", f"${summary['money_owed_to_you']:,.2f}")
    table.add_row("Money You Owe", f"${summary['money_you_owe']:,.2f}")
    table.add_row("Pending Action Items", str(summary["pending_actions"]))
    table.add_section()
    table.add_row("Active Song Orders (CC)", str(summary["active_song_orders"]))
    table.add_row("Song Orders Pipeline Value", f"${summary['song_orders_pipeline_value']:,.2f}")
    console.print(table)

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

    scheduler = TrackerScheduler(
        fetch_fn=lambda: do_fetch(config),
        analyze_fn=lambda: do_analyze(config),
        digest_fn=lambda dt: do_digest(config, dt),
        config=config,
    )

    console.print("[bold]Starting scheduled tracker...[/bold]")
    console.print("Running initial fetch + analyze cycle...")
    do_fetch(config)
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


if __name__ == "__main__":
    cli()
