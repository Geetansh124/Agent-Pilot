"""Database access, event store, and projection operations for DeepSeek Harness."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from typing import Any, Optional

from src.auth.database import get_db_connection, _ensure_user_exists
from src.harness.config import get_harness_settings


def init_harness_tables(cursor: sqlite3.Cursor) -> None:
    """Ensure all harness schema tables exist."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS harness_sessions (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            harness_session_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            last_event_seq INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(thread_id)
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS harness_events (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload JSON NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(thread_id, seq)
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS harness_approvals (
            id TEXT PRIMARY KEY,
            request_id TEXT UNIQUE NOT NULL,
            thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
            tool_name TEXT NOT NULL,
            arguments JSON NOT NULL,
            decision TEXT NOT NULL CHECK(decision IN ('pending', 'allowed-once', 'rejected', 'cancelled')),
            decided_by TEXT REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            decided_at TIMESTAMP
        );
    """)


def upsert_harness_session(
    thread_id: str,
    user_id: str,
    harness_session_id: str,
    status: str = "active",
    last_event_seq: int = 0,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Upsert a mapping between thread and harness session."""
    session_pk = str(uuid.uuid4())
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        init_harness_tables(cursor)
        _ensure_user_exists(cursor, user_id)
        cursor.execute(
            """
            INSERT INTO threads (id, user_id, title)
            VALUES (?, ?, 'New chat')
            ON CONFLICT(id) DO NOTHING
            """,
            (thread_id, user_id),
        )
        cursor.execute(
            """
            INSERT INTO harness_sessions (id, thread_id, user_id, harness_session_id, status, last_event_seq)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                harness_session_id = excluded.harness_session_id,
                status = excluded.status,
                last_event_seq = MAX(harness_sessions.last_event_seq, excluded.last_event_seq),
                updated_at = CURRENT_TIMESTAMP
            """,
            (session_pk, thread_id, user_id, harness_session_id, status, last_event_seq),
        )
        conn.commit()
    return get_harness_session(thread_id, db_path=db_path) or {}


def get_harness_session(thread_id: str, db_path: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Retrieve harness session record by thread ID."""
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, thread_id, user_id, harness_session_id, status, last_event_seq, created_at, updated_at "
                "FROM harness_sessions WHERE thread_id = ?",
                (thread_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    except sqlite3.OperationalError:
        return None


def verify_session_ownership(thread_id: str, user_id: str, db_path: Optional[str] = None) -> bool:
    """Verify if user is the legitimate owner of the harness session for this thread."""
    session = get_harness_session(thread_id, db_path=db_path)
    if not session:
        return True
    return session["user_id"] == user_id


def append_harness_event(
    thread_id: str,
    seq: int,
    event_type: str,
    payload: dict[str, Any],
    user_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Idempotently append an event and project assistant messages into SQLite messages table."""
    event_pk = str(uuid.uuid4())
    payload_str = json.dumps(payload, default=str)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        init_harness_tables(cursor)

        # Idempotent append
        cursor.execute(
            """
            INSERT INTO harness_events (id, thread_id, seq, event_type, payload)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(thread_id, seq) DO NOTHING
            """,
            (event_pk, thread_id, seq, event_type, payload_str),
        )
        cursor.execute(
            """
            UPDATE harness_sessions
            SET last_event_seq = MAX(last_event_seq, ?), updated_at = CURRENT_TIMESTAMP
            WHERE thread_id = ?
            """,
            (seq, thread_id),
        )

        # Atomic projection to messages table when assistant message commits
        if event_type == "assistant/message":
            msg_content = str(payload.get("content", ""))
            tools = payload.get("tool_calls", [])
            msg_pk = f"proj-{thread_id}-{seq}"
            cursor.execute(
                """
                INSERT INTO messages (id, thread_id, role, content, tool_calls)
                VALUES (?, ?, 'assistant', ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (msg_pk, thread_id, msg_content, json.dumps(tools) if tools else None),
            )
        conn.commit()
    return True


def get_harness_events(thread_id: str, db_path: Optional[str] = None) -> list[dict[str, Any]]:
    """Retrieve all harness events for a thread ordered by sequence number."""
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT seq, event_type, payload, created_at FROM harness_events WHERE thread_id = ? ORDER BY seq ASC",
                (thread_id,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "seq": r["seq"],
                    "event_type": r["event_type"],
                    "payload": json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
    except sqlite3.OperationalError:
        return []


def clean_thread_persistence(
    thread_id: str,
    user_id: str,
    settings: Optional[Any] = None,
    db_path: Optional[str] = None,
) -> None:
    """Clean all database rows and local workspace files when thread is deleted."""
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM harness_events WHERE thread_id = ?", (thread_id,))
            cursor.execute("DELETE FROM harness_approvals WHERE thread_id = ?", (thread_id,))
            cursor.execute("DELETE FROM harness_sessions WHERE thread_id = ?", (thread_id,))
            conn.commit()
    except Exception:
        pass

    active_settings = settings or get_harness_settings()
    ws = active_settings.get_thread_workspace(user_id, thread_id)
    if os.path.exists(ws):
        try:
            shutil.rmtree(ws, ignore_errors=True)
        except Exception:
            pass
