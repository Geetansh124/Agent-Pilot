"""Database access, event store, and projection operations for DeepSeek Harness."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from src.auth.database import get_db_connection, _ensure_user_exists


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
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, thread_id, user_id, harness_session_id, status, last_event_seq, created_at, updated_at "
            "FROM harness_sessions WHERE thread_id = ?",
            (thread_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def verify_session_ownership(thread_id: str, user_id: str, db_path: Optional[str] = None) -> bool:
    """Verify if user is the legitimate owner of the harness session for this thread."""
    session = get_harness_session(thread_id, db_path=db_path)
    if not session:
        return True  # Thread not yet bound to a session
    return session["user_id"] == user_id
