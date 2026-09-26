"""Audit logging subsystem.

Records all system interactions, tool calls, authorization events, and errors
into a persistent SQLite ledger for compliance and forensic analysis.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

DB_PATH = "chatbot.db"


def _get_audit_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            duration_ms REAL DEFAULT 0.0,
            details TEXT
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_thread ON audit_logs (thread_id, event_type)"
    )
    conn.commit()
    return conn


class AuditLogger:
    """Manages recording and querying audit event records."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = _get_audit_conn(db_path)

    def log(
        self,
        event_type: str,
        action: str,
        thread_id: str = "global",
        user_id: str = "guest",
        status: str = "success",
        duration_ms: float = 0.0,
        details: Optional[dict[str, Any]] = None,
    ) -> int:
        """Record an audit trail event."""
        cursor = self.conn.cursor()
        now_utc = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """INSERT INTO audit_logs (timestamp, event_type, thread_id, user_id, action, status, duration_ms, details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                now_utc,
                event_type.strip(),
                thread_id.strip() if thread_id else "global",
                user_id.strip() if user_id else "guest",
                action.strip()[:200],
                status.strip(),
                round(duration_ms, 2),
                json.dumps(details or {}),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid or 0

    def query(
        self,
        thread_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve recent audit logs."""
        cursor = self.conn.cursor()
        clauses = []
        params = []
        if thread_id:
            clauses.append("thread_id = ?")
            params.append(thread_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query_sql = f"SELECT id, timestamp, event_type, thread_id, user_id, action, status, duration_ms, details FROM audit_logs {where_sql} ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))

        cursor.execute(query_sql, tuple(params))
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "timestamp": r[1],
                "event_type": r[2],
                "thread_id": r[3],
                "user_id": r[4],
                "action": r[5],
                "status": r[6],
                "duration_ms": r[7],
                "details": json.loads(r[8]) if r[8] else {},
            }
            for r in rows
        ]


audit_logger = AuditLogger()
