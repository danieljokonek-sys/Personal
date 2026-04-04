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
            account_email TEXT,          -- which Gmail account this came from
            sender TEXT,
            recipients TEXT,
            subject TEXT,
            body_snippet TEXT,
            date TEXT,
            labels TEXT,
            entity_key TEXT,
            is_sms_forward INTEGER DEFAULT 0,
            processed INTEGER DEFAULT 0,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS calendar_events (
            event_id TEXT PRIMARY KEY,
            calendar_id TEXT,
            calendar_name TEXT,
            account_email TEXT,
            title TEXT,
            description TEXT,
            location TEXT,
            start_date TEXT,
            start_datetime TEXT,
            end_date TEXT,
            end_datetime TEXT,
            all_day INTEGER DEFAULT 0,
            attendees TEXT,
            status TEXT DEFAULT 'confirmed',
            entity_key TEXT,
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

        -- Chorus Crafters: custom song order pipeline
        CREATE TABLE IF NOT EXISTS song_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Source traceability
            email_id TEXT REFERENCES emails(id),

            -- Client
            client_name TEXT,
            client_email TEXT,
            client_phone TEXT,

            -- Event
            event_type TEXT,      -- wedding | memorial | birthday | anniversary | other
            event_date TEXT,      -- YYYY-MM-DD, the performance/occasion date
            honoree_names TEXT,   -- "John & Jane Smith", "In Memory of Bob"
            event_notes TEXT,     -- venue, context, anything else

            -- Song brief
            song_style TEXT,      -- genre, mood, vibe, instrumentation
            song_story TEXT,      -- the narrative / details to weave in
            reference_songs TEXT, -- JSON array of reference track titles/artists

            -- Revisions
            revisions_included INTEGER DEFAULT 2,
            revisions_used INTEGER DEFAULT 0,

            -- Financials
            price REAL,
            deposit_amount REAL,
            deposit_paid INTEGER DEFAULT 0,   -- 0/1 boolean
            deposit_date TEXT,
            balance_due REAL,
            balance_paid INTEGER DEFAULT 0,
            balance_date TEXT,

            -- Delivery milestones
            demo_delivered INTEGER DEFAULT 0,
            demo_date TEXT,
            final_delivered INTEGER DEFAULT 0,
            final_date TEXT,

            -- Status pipeline:
            -- inquiry → quoted → deposit_received → in_production →
            -- revision_requested → in_revision → delivered → complete | cancelled
            status TEXT DEFAULT 'inquiry',

            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_emails_entity ON emails(entity_key);
        CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(date);
        CREATE INDEX IF NOT EXISTS idx_emails_account ON emails(account_email);
        CREATE INDEX IF NOT EXISTS idx_deadlines_due ON deadlines(due_date);
        CREATE INDEX IF NOT EXISTS idx_deadlines_status ON deadlines(status);
        CREATE INDEX IF NOT EXISTS idx_financial_status ON financial_items(status);
        CREATE INDEX IF NOT EXISTS idx_financial_direction ON financial_items(direction);
        CREATE INDEX IF NOT EXISTS idx_action_status ON action_items(status);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON song_orders(status);
        CREATE INDEX IF NOT EXISTS idx_orders_event_date ON song_orders(event_date);
        CREATE INDEX IF NOT EXISTS idx_cal_start ON calendar_events(start_datetime, start_date);
        CREATE INDEX IF NOT EXISTS idx_cal_account ON calendar_events(account_email);
    """)
    conn.commit()
    conn.close()


def store_email(email: dict):
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO emails
           (id, thread_id, account_email, sender, recipients, subject,
            body_snippet, date, labels, entity_key, is_sms_forward)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            email["id"],
            email.get("thread_id"),
            email.get("account_email", ""),
            email.get("sender"),
            json.dumps(email.get("recipients", [])),
            email.get("subject"),
            email.get("body_snippet", "")[:2000],
            email.get("date"),
            json.dumps(email.get("labels", [])),
            email.get("entity_key"),
            1 if email.get("is_sms_forward") else 0,
        ),
    )
    conn.commit()
    conn.close()


def store_calendar_events(events: list[dict]):
    """Upsert a list of calendar events."""
    conn = get_connection()
    for ev in events:
        conn.execute(
            """INSERT OR REPLACE INTO calendar_events
               (event_id, calendar_id, calendar_name, account_email,
                title, description, location,
                start_date, start_datetime, end_date, end_datetime,
                all_day, attendees, status, entity_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ev["event_id"],
                ev.get("calendar_id"),
                ev.get("calendar_name"),
                ev.get("account_email"),
                ev.get("title"),
                ev.get("description", ""),
                ev.get("location", ""),
                ev.get("start_date"),
                ev.get("start_datetime"),
                ev.get("end_date"),
                ev.get("end_datetime"),
                1 if ev.get("all_day") else 0,
                json.dumps(ev.get("attendees", [])),
                ev.get("status", "confirmed"),
                ev.get("entity_key"),
            ),
        )
    conn.commit()
    conn.close()


def get_upcoming_events(days_ahead: int = 14) -> list[dict]:
    """Return calendar events starting within the next N days."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM calendar_events
           WHERE status != 'cancelled'
             AND (
               (start_datetime IS NOT NULL AND start_datetime >= datetime('now')
                AND start_datetime <= datetime('now', '+' || ? || ' days'))
               OR
               (start_date IS NOT NULL AND start_datetime IS NULL
                AND start_date >= date('now')
                AND start_date <= date('now', '+' || ? || ' days'))
             )
           ORDER BY COALESCE(start_datetime, start_date) ASC""",
        (days_ahead, days_ahead),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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


# ── Song Orders (Chorus Crafters) ─────────────────────────────────────────────

ACTIVE_ORDER_STATUSES = (
    "inquiry", "quoted", "deposit_received",
    "in_production", "revision_requested", "in_revision", "delivered",
)


def upsert_song_order(order: dict) -> int:
    """Insert or update a song order. Returns the row id."""
    conn = get_connection()
    now = datetime.utcnow().isoformat()

    # Try to match an existing order by client email + event date, or client name
    existing_id = None
    if order.get("client_email") and order.get("event_date"):
        row = conn.execute(
            "SELECT id FROM song_orders WHERE client_email = ? AND event_date = ?",
            (order["client_email"], order["event_date"]),
        ).fetchone()
        existing_id = row["id"] if row else None

    if not existing_id and order.get("client_name") and order.get("event_date"):
        row = conn.execute(
            "SELECT id FROM song_orders WHERE client_name = ? AND event_date = ?",
            (order["client_name"], order["event_date"]),
        ).fetchone()
        existing_id = row["id"] if row else None

    if existing_id:
        # Update non-null fields only
        fields = [
            "client_name", "client_email", "client_phone",
            "event_type", "event_date", "honoree_names", "event_notes",
            "song_style", "song_story", "reference_songs",
            "revisions_included", "price", "deposit_amount",
            "balance_due", "notes", "status",
        ]
        updates = {f: order[f] for f in fields if f in order and order[f] is not None}
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE song_orders SET {set_clause}, updated_at = ? WHERE id = ?",
                [*updates.values(), now, existing_id],
            )
        conn.commit()
        conn.close()
        return existing_id
    else:
        cur = conn.execute(
            """INSERT INTO song_orders (
                email_id, client_name, client_email, client_phone,
                event_type, event_date, honoree_names, event_notes,
                song_style, song_story, reference_songs,
                revisions_included, price, deposit_amount, balance_due,
                status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order.get("email_id"),
                order.get("client_name"),
                order.get("client_email"),
                order.get("client_phone"),
                order.get("event_type"),
                order.get("event_date"),
                order.get("honoree_names"),
                order.get("event_notes"),
                order.get("song_style"),
                order.get("song_story"),
                json.dumps(order.get("reference_songs", [])),
                order.get("revisions_included", 2),
                order.get("price"),
                order.get("deposit_amount"),
                order.get("balance_due"),
                order.get("status", "inquiry"),
                order.get("notes"),
                now,
                now,
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return new_id


def update_order(order_id: int, fields: dict):
    """Update specific fields on a song order."""
    allowed = {
        "client_name", "client_email", "client_phone",
        "event_type", "event_date", "honoree_names", "event_notes",
        "song_style", "song_story", "reference_songs",
        "revisions_included", "revisions_used",
        "price", "deposit_amount", "deposit_paid", "deposit_date",
        "balance_due", "balance_paid", "balance_date",
        "demo_delivered", "demo_date", "final_delivered", "final_date",
        "status", "notes",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    conn = get_connection()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE song_orders SET {set_clause}, updated_at = ? WHERE id = ?",
        [*updates.values(), datetime.utcnow().isoformat(), order_id],
    )
    conn.commit()
    conn.close()


def get_order(order_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM song_orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_orders() -> list[dict]:
    placeholders = ",".join("?" * len(ACTIVE_ORDER_STATUSES))
    conn = get_connection()
    rows = conn.execute(
        f"SELECT * FROM song_orders WHERE status IN ({placeholders}) ORDER BY event_date ASC NULLS LAST",
        ACTIVE_ORDER_STATUSES,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_orders_by_status(status: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM song_orders WHERE status = ? ORDER BY event_date ASC NULLS LAST",
        (status,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_orders(include_closed: bool = False) -> list[dict]:
    conn = get_connection()
    if include_closed:
        rows = conn.execute(
            "SELECT * FROM song_orders ORDER BY event_date ASC NULLS LAST"
        ).fetchall()
    else:
        placeholders = ",".join("?" * len(ACTIVE_ORDER_STATUSES))
        rows = conn.execute(
            f"SELECT * FROM song_orders WHERE status IN ({placeholders}) ORDER BY event_date ASC NULLS LAST",
            ACTIVE_ORDER_STATUSES,
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_orders_pipeline_summary() -> dict:
    """Revenue and count breakdown by status for the Chorus Crafters pipeline."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT status,
                  COUNT(*) as count,
                  COALESCE(SUM(price), 0) as total_value,
                  COALESCE(SUM(CASE WHEN deposit_paid = 1 THEN deposit_amount ELSE 0 END), 0) as deposits_collected,
                  COALESCE(SUM(CASE WHEN balance_paid = 1 THEN balance_due ELSE 0 END), 0) as balances_collected
           FROM song_orders
           WHERE status NOT IN ('cancelled')
           GROUP BY status"""
    ).fetchall()
    conn.close()
    return {r["status"]: dict(r) for r in rows}


def get_dashboard_summary() -> dict:
    """Get counts for the status dashboard."""
    conn = get_connection()

    placeholders = ",".join("?" * len(ACTIVE_ORDER_STATUSES))
    active_orders_row = conn.execute(
        f"SELECT COUNT(*) c, COALESCE(SUM(price),0) v FROM song_orders WHERE status IN ({placeholders})",
        ACTIVE_ORDER_STATUSES,
    ).fetchone()

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
        "active_song_orders": active_orders_row["c"],
        "song_orders_pipeline_value": active_orders_row["v"],
        "upcoming_events_7d": conn.execute(
            """SELECT COUNT(*) c FROM calendar_events
               WHERE status != 'cancelled'
                 AND COALESCE(start_datetime, start_date) >= date('now')
                 AND COALESCE(start_datetime, start_date) <= date('now', '+7 days')"""
        ).fetchone()["c"],
    }
    conn.close()
    return summary
