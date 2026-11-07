"""SQLite storage for subscribers, reminders and payments.

Fine for one server with a persistent disk. Move to Postgres (e.g. Supabase)
before running more than one instance.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    phone TEXT PRIMARY KEY,
    name TEXT,
    state TEXT NOT NULL DEFAULT 'idle',
    draft TEXT,
    subscribed_until TEXT,
    last_inbound_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    task TEXT NOT NULL,
    casual_text TEXT,
    vivid_kind TEXT NOT NULL,            -- 'text' or 'voice'
    vivid_text TEXT,                     -- what the user typed (or transcript of the voice note)
    reminder_text TEXT NOT NULL,         -- reporting form, e.g. "Time to call mom to ..."
    audio_path TEXT,
    audio_mime TEXT,
    due_at TEXT NOT NULL,                -- UTC ISO-8601
    status TEXT NOT NULL DEFAULT 'pending', -- pending|sending|awaiting_play|sent|cancelled|failed
    error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status, due_at);
CREATE TABLE IF NOT EXISTS message_map (
    wa_message_id TEXT PRIMARY KEY,      -- WhatsApp message id -> reminder it belongs to
    reminder_id INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS processed_messages (
    id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    reference TEXT PRIMARY KEY,
    phone TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


# Columns added after the first release; added to older databases on start-up.
REMINDER_MIGRATIONS = {
    "who": "TEXT",              # person involved, e.g. "driver Kwame"
    "fired_at": "TEXT",
    "delivery": "TEXT",         # WhatsApp: sent | delivered | read | failed
    "sms_sent_at": "TEXT",
    "outcome": "TEXT",          # done | missed (NULL while upcoming or waiting)
    "outcome_at": "TEXT",
}
DELIVERY_RANK = {"failed": 0, "sent": 1, "delivered": 2, "read": 3}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Database:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        existing = {row["name"] for row in self._conn.execute("PRAGMA table_info(reminders)")}
        for column, kind in REMINDER_MIGRATIONS.items():
            if column not in existing:
                self._conn.execute(f"ALTER TABLE reminders ADD COLUMN {column} {kind}")
        self._lock = RLock()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    # ---- de-duplication (Meta re-delivers webhooks) ----
    def mark_processed(self, message_id: str) -> bool:
        """Returns False if this WhatsApp message id was already handled."""
        cur = self._exec(
            "INSERT OR IGNORE INTO processed_messages (id, received_at) VALUES (?, ?)",
            (message_id, iso(utcnow())),
        )
        return cur.rowcount == 1

    # ---- users ----
    def get_or_create_user(self, phone: str, name: str | None = None) -> dict:
        self._exec(
            "INSERT OR IGNORE INTO users (phone, name, created_at) VALUES (?, ?, ?)",
            (phone, name, iso(utcnow())),
        )
        if name:
            self._exec("UPDATE users SET name = ? WHERE phone = ?", (name, phone))
        return self.get_user(phone)

    def get_user(self, phone: str) -> dict | None:
        row = self._exec("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        if not row:
            return None
        user = dict(row)
        user["draft"] = json.loads(user["draft"]) if user["draft"] else None
        return user

    def touch_inbound(self, phone: str) -> None:
        self._exec("UPDATE users SET last_inbound_at = ? WHERE phone = ?", (iso(utcnow()), phone))

    def set_state(self, phone: str, state: str, draft: dict | None = None) -> None:
        self._exec(
            "UPDATE users SET state = ?, draft = ? WHERE phone = ?",
            (state, json.dumps(draft) if draft is not None else None, phone),
        )

    def set_subscribed_until(self, phone: str, until: datetime) -> None:
        self.get_or_create_user(phone)
        self._exec("UPDATE users SET subscribed_until = ? WHERE phone = ?", (iso(until), phone))

    # ---- reminders ----
    def add_reminder(self, **fields) -> int:
        fields.setdefault("created_at", iso(utcnow()))
        columns = ", ".join(fields)
        placeholders = ", ".join("?" for _ in fields)
        cur = self._exec(f"INSERT INTO reminders ({columns}) VALUES ({placeholders})", tuple(fields.values()))
        return cur.lastrowid

    def get_reminder(self, reminder_id: int) -> dict | None:
        row = self._exec("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return dict(row) if row else None

    def pending_reminders(self, phone: str) -> list[dict]:
        rows = self._exec(
            "SELECT * FROM reminders WHERE phone = ? AND status = 'pending' ORDER BY due_at", (phone,)
        ).fetchall()
        return [dict(r) for r in rows]

    def awaiting_play(self, phone: str) -> list[dict]:
        rows = self._exec(
            "SELECT * FROM reminders WHERE phone = ? AND status = 'awaiting_play' ORDER BY due_at", (phone,)
        ).fetchall()
        return [dict(r) for r in rows]

    def cancel_reminder(self, phone: str, reminder_id: int) -> bool:
        cur = self._exec(
            "UPDATE reminders SET status = 'cancelled' WHERE id = ? AND phone = ? AND status = 'pending'",
            (reminder_id, phone),
        )
        return cur.rowcount == 1

    def claim_due(self, now: datetime) -> list[dict]:
        """Atomically moves due reminders to 'sending' so each fires once."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM reminders WHERE status = 'pending' AND due_at <= ? ORDER BY due_at", (iso(now),)
            ).fetchall()
            claimed = []
            for row in rows:
                cur = self._conn.execute(
                    "UPDATE reminders SET status = 'sending' WHERE id = ? AND status = 'pending'", (row["id"],)
                )
                if cur.rowcount == 1:
                    claimed.append(self.get_reminder(row["id"]))
            return claimed

    def set_reminder_status(self, reminder_id: int, status: str, error: str | None = None) -> None:
        sent_at = iso(utcnow()) if status == "sent" else None
        fired_at = iso(utcnow()) if status in ("sent", "awaiting_play", "failed") else None
        self._exec(
            "UPDATE reminders SET status = ?, error = ?, sent_at = COALESCE(?, sent_at),"
            " fired_at = COALESCE(fired_at, ?) WHERE id = ?",
            (status, error, sent_at, fired_at, reminder_id),
        )

    # ---- WhatsApp delivery tracking ----
    def link_message(self, wa_message_id: str | None, reminder_id: int) -> None:
        if not wa_message_id:
            return
        self._exec(
            "INSERT OR REPLACE INTO message_map (wa_message_id, reminder_id) VALUES (?, ?)",
            (wa_message_id, reminder_id),
        )
        self._exec("UPDATE reminders SET delivery = COALESCE(delivery, 'sent') WHERE id = ?", (reminder_id,))

    def record_delivery(self, wa_message_id: str, status: str) -> dict | None:
        """Applies a WhatsApp status update; never downgrades (read > delivered > sent)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT r.* FROM message_map m JOIN reminders r ON r.id = m.reminder_id WHERE m.wa_message_id = ?",
                (wa_message_id,),
            ).fetchone()
            if not row:
                return None
            current = DELIVERY_RANK.get(row["delivery"] or "", -1)
            new = DELIVERY_RANK.get(status, -1)
            if status == "failed" and current >= DELIVERY_RANK["delivered"]:
                return dict(row)
            if new > current or status == "failed":
                self._conn.execute("UPDATE reminders SET delivery = ? WHERE id = ?", (status, row["id"]))
            return self.get_reminder(row["id"])

    def needing_sms(self, fired_before: datetime) -> list[dict]:
        """Fired reminders that WhatsApp hasn't delivered to the phone in time."""
        rows = self._exec(
            "SELECT * FROM reminders WHERE sms_sent_at IS NULL AND fired_at IS NOT NULL AND fired_at <= ?"
            " AND status IN ('sent', 'awaiting_play', 'failed')"
            " AND COALESCE(delivery, 'none') NOT IN ('delivered', 'read')",
            (iso(fired_before),),
        ).fetchall()
        return [dict(r) for r in rows]

    def claim_sms(self, reminder_id: int) -> bool:
        cur = self._exec(
            "UPDATE reminders SET sms_sent_at = ? WHERE id = ? AND sms_sent_at IS NULL", (iso(utcnow()), reminder_id)
        )
        return cur.rowcount == 1

    def release_sms(self, reminder_id: int) -> None:
        self._exec("UPDATE reminders SET sms_sent_at = NULL WHERE id = ?", (reminder_id,))

    # ---- Done / Missed / Upcoming ----
    def set_outcome(self, phone: str, reminder_id: int, outcome: str) -> bool:
        cur = self._exec(
            "UPDATE reminders SET outcome = ?, outcome_at = ? WHERE id = ? AND phone = ?"
            " AND fired_at IS NOT NULL AND status != 'cancelled'",
            (outcome, iso(utcnow()), reminder_id, phone),
        )
        return cur.rowcount == 1

    def latest_open(self, phone: str) -> dict | None:
        row = self._exec(
            "SELECT * FROM reminders WHERE phone = ? AND fired_at IS NOT NULL AND outcome IS NULL"
            " AND status != 'cancelled' ORDER BY fired_at DESC LIMIT 1",
            (phone,),
        ).fetchone()
        return dict(row) if row else None

    def sweep_missed(self, fired_before: datetime) -> int:
        cur = self._exec(
            "UPDATE reminders SET outcome = 'missed', outcome_at = ? WHERE outcome IS NULL"
            " AND fired_at IS NOT NULL AND fired_at <= ? AND status != 'cancelled'",
            (iso(utcnow()), iso(fired_before)),
        )
        return cur.rowcount

    def finished_since(self, phone: str, since: datetime) -> list[dict]:
        rows = self._exec(
            "SELECT * FROM reminders WHERE phone = ? AND fired_at IS NOT NULL AND status != 'cancelled'"
            " AND fired_at >= ? ORDER BY fired_at DESC",
            (phone, iso(since)),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- data deletion ----
    def delete_user_data(self, phone: str) -> list[str]:
        """Deletes a subscriber's profile and reminders. Returns saved voice-note paths to remove.

        Payment records (reference + phone) are kept for accounting, as the privacy page says.
        """
        with self._lock:
            paths = [
                r["audio_path"] for r in self._conn.execute(
                    "SELECT audio_path FROM reminders WHERE phone = ? AND audio_path IS NOT NULL", (phone,)
                ).fetchall()
            ]
            self._conn.execute(
                "DELETE FROM message_map WHERE reminder_id IN (SELECT id FROM reminders WHERE phone = ?)", (phone,)
            )
            self._conn.execute("DELETE FROM reminders WHERE phone = ?", (phone,))
            self._conn.execute("DELETE FROM users WHERE phone = ?", (phone,))
            return paths

    # ---- payments ----
    def add_payment(self, reference: str, phone: str) -> None:
        self._exec(
            "INSERT OR IGNORE INTO payments (reference, phone, status, created_at) VALUES (?, ?, 'initialized', ?)",
            (reference, phone, iso(utcnow())),
        )

    def complete_payment(self, reference: str) -> str | None:
        """Marks a payment paid once; returns the phone, or None if unknown/already paid."""
        with self._lock:
            row = self._conn.execute(
                "SELECT phone, status FROM payments WHERE reference = ?", (reference,)
            ).fetchone()
            if not row or row["status"] == "paid":
                return None
            self._conn.execute("UPDATE payments SET status = 'paid' WHERE reference = ?", (reference,))
            return row["phone"]
