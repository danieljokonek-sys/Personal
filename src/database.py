"""
SQLite storage for tracked communications, agreements, deadlines, and finances.
"""
import sqlite3
import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional


DB_PATH = Path("data/tracker.db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS emails (
            id TEXT PRIMARY KEY,
            thread_id TEXT,
            sender TEXT,
            recipients TEXT,
            subject TEXT,
            body_snippet TEXT,
            date TEXT,
            labels TEXT,
            entity_key TEXT,
            processed INTEGER DEFAULT 0,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agreements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT REFERENCES emails(id),
            entity_key TEXT,
            summary TEXT NOT NULL,
            parties TEXT,
            terms TEXT,
            status TEXT DEFAULT 'active',
            source_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS deadlines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT REFERENCES emails(id),
            entity_key TEXT,
            description TEXT NOT NULL,
            due_date TEXT,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'pending',
            source_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS financial_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT REFERENCES emails(id),
            entity_key TEXT,
            direction TEXT NOT NULL,
            counterparty TEXT,
            amount REAL,
            currency TEXT DEFAULT 'USD',
            description TEXT,
            due_date TEXT,
            status TEXT DEFAULT 'pending',
            source_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS action_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT REFERENCES emails(id),
            entity_key TEXT,
            description TEXT NOT NULL,
            assigned_to TEXT,
            due_date TEXT,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'pending',
            source_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_emails_entity ON emails(entity_key);
        CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(date);
        CREATE INDEX IF NOT EXISTS idx_deadlines_due ON deadlines(due_date);
        CREATE INDEX IF NOT EXISTS idx_deadlines_status ON deadlines(status);
        CREATE INDEX IF NOT EXISTS idx_financial_status ON financial_items(status);
        CREATE INDEX IF NOT EXISTS idx_financial_direction ON financial_items(direction);
        CREATE INDEX IF NOT EXISTS idx_action_status ON action_items(status);
    """)
    conn.commit()
    conn.close()


def store_email(email: dict):
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO emails
           (id, thread_id, sender, recipients, subject, body_snippet, date, labels, entity_key)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            email["id"],
            email.get("thread_id"),
            email.get("sender"),
            json.dumps(email.get("recipients", [])),
            email.get("subject"),
            email.get("body_snippet", "")[:2000],
            email.get("date"),
            json.dumps(email.get("labels", [])),
            email.get("entity_key"),
        ),
    )
    conn.commit()
    conn.close()


def store_extractions(email_id: str, extractions: dict):
    """Store all extracted items from Claude's analysis."""
    conn = get_connection()

    for agreement in extractions.get("agreements", []):
        conn.execute(
            """INSERT INTO agreements (email_id, entity_key, summary, parties, terms, source_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                email_id,
                agreement.get("entity_key"),
                agreement["summary"],
                json.dumps(agreement.get("parties", [])),
                agreement.get("terms"),
                agreement.get("source_date"),
            ),
        )

    for deadline in extractions.get("deadlines", []):
        conn.execute(
            """INSERT INTO deadlines (email_id, entity_key, description, due_date, priority, source_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                email_id,
                deadline.get("entity_key"),
                deadline["description"],
                deadline.get("due_date"),
                deadline.get("priority", "medium"),
                deadline.get("source_date"),
            ),
        )

    for item in extractions.get("financial_items", []):
        conn.execute(
            """INSERT INTO financial_items
               (email_id, entity_key, direction, counterparty, amount, currency, description, due_date, source_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                email_id,
                item.get("entity_key"),
                item["direction"],
                item.get("counterparty"),
                item.get("amount"),
                item.get("currency", "USD"),
                item.get("description"),
                item.get("due_date"),
                item.get("source_date"),
            ),
        )

    for action in extractions.get("action_items", []):
        conn.execute(
            """INSERT INTO action_items
               (email_id, entity_key, description, assigned_to, due_date, priority, source_date)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                email_id,
                action.get("entity_key"),
                action["description"],
                action.get("assigned_to"),
                action.get("due_date"),
                action.get("priority", "medium"),
                action.get("source_date"),
            ),
        )

    # Mark email as processed
    conn.execute("UPDATE emails SET processed = 1 WHERE id = ?", (email_id,))
    conn.commit()
    conn.close()


def mark_email_processed(email_id: str):
    conn = get_connection()
    conn.execute("UPDATE emails SET processed = 1 WHERE id = ?", (email_id,))
    conn.commit()
    conn.close()


def get_unprocessed_emails(limit: int = 100) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM emails WHERE processed = 0 ORDER BY date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_deadlines(days_ahead: int = 14) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT d.*, e.subject as email_subject, e.sender as email_sender
           FROM deadlines d
           LEFT JOIN emails e ON d.email_id = e.id
           WHERE d.status = 'pending'
             AND d.due_date IS NOT NULL
             AND d.due_date <= date('now', '+' || ? || ' days')
           ORDER BY d.due_date ASC""",
        (days_ahead,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_financial(direction: Optional[str] = None) -> list[dict]:
    conn = get_connection()
    if direction:
        rows = conn.execute(
            """SELECT f.*, e.subject as email_subject, e.sender as email_sender
               FROM financial_items f
               LEFT JOIN emails e ON f.email_id = e.id
               WHERE f.status = 'pending' AND f.direction = ?
               ORDER BY f.due_date ASC NULLS LAST""",
            (direction,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT f.*, e.subject as email_subject, e.sender as email_sender
               FROM financial_items f
               LEFT JOIN emails e ON f.email_id = e.id
               WHERE f.status = 'pending'
               ORDER BY f.direction, f.due_date ASC NULLS LAST"""
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_active_agreements() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.*, e.subject as email_subject, e.sender as email_sender
           FROM agreements a
           LEFT JOIN emails e ON a.email_id = e.id
           WHERE a.status = 'active'
           ORDER BY a.created_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_actions() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.*, e.subject as email_subject, e.sender as email_sender
           FROM action_items a
           LEFT JOIN emails e ON a.email_id = e.id
           WHERE a.status = 'pending'
           ORDER BY a.priority DESC, a.due_date ASC NULLS LAST"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sync_state(key: str) -> Optional[str]:
    conn = get_connection()
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def set_sync_state(key: str, value: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def update_item_status(table: str, item_id: int, status: str):
    allowed_tables = {"agreements", "deadlines", "financial_items", "action_items"}
    if table not in allowed_tables:
        raise ValueError(f"Invalid table: {table}")
    conn = get_connection()
    conn.execute(f"UPDATE {table} SET status = ? WHERE id = ?", (status, item_id))
    conn.commit()
    conn.close()


def get_dashboard_summary() -> dict:
    """Get counts for the status dashboard."""
    conn = get_connection()
    summary = {
        "total_emails": conn.execute("SELECT COUNT(*) c FROM emails").fetchone()["c"],
        "unprocessed_emails": conn.execute(
            "SELECT COUNT(*) c FROM emails WHERE processed = 0"
        ).fetchone()["c"],
        "active_agreements": conn.execute(
            "SELECT COUNT(*) c FROM agreements WHERE status = 'active'"
        ).fetchone()["c"],
        "pending_deadlines": conn.execute(
            "SELECT COUNT(*) c FROM deadlines WHERE status = 'pending'"
        ).fetchone()["c"],
        "money_owed_to_you": conn.execute(
            "SELECT COALESCE(SUM(amount), 0) c FROM financial_items WHERE direction = 'receivable' AND status = 'pending'"
        ).fetchone()["c"],
        "money_you_owe": conn.execute(
            "SELECT COALESCE(SUM(amount), 0) c FROM financial_items WHERE direction = 'payable' AND status = 'pending'"
        ).fetchone()["c"],
        "pending_actions": conn.execute(
            "SELECT COUNT(*) c FROM action_items WHERE status = 'pending'"
        ).fetchone()["c"],
    }
    conn.close()
    return summary
