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
)
from src.gmail_client import GmailClient
from src.analyzer import Analyzer
from src.digest import DigestGenerator
from src.scheduler import TrackerScheduler

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


if __name__ == "__main__":
    cli()
