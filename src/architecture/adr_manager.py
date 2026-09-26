"""Architecture Decision Record (ADR) Management Engine.

Maintains structured, immutable architectural decisions capturing Title, Context,
Decision, Consequences, and Status (Proposed, Accepted, Deprecated, Superseded).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from langchain_core.tools import tool

DB_PATH = "chatbot.db"


class ADRStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


@dataclass
class ADRRecord:
    id: int
    title: str
    status: str
    context: str
    decision: str
    consequences: str
    tags: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        tag_str = ", ".join(self.tags) if self.tags else "None"
        return f"""# ADR-{self.id:04d}: {self.title}

- **Status**: {self.status.upper()}
- **Date**: {self.created_at[:10]}
- **Tags**: {tag_str}

## Context
{self.context}

## Decision
{self.decision}

## Consequences
{self.consequences}
"""


def _get_adr_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS adr_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'accepted',
            context TEXT NOT NULL,
            decision TEXT NOT NULL,
            consequences TEXT NOT NULL,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.commit()
    return conn


class ADRManager:
    """Manages Architecture Decision Records stored in SQLite with Markdown generation."""

    def __init__(self, db_path: str = DB_PATH):
        self.conn = _get_adr_conn(db_path)

    def create_adr(
        self,
        title: str,
        context: str,
        decision: str,
        consequences: str,
        status: str = "accepted",
        tags: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Record a new architecture decision."""
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        tags_json = json.dumps(tags or [])
        cursor.execute(
            """INSERT INTO adr_records (title, status, context, decision, consequences, tags, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title.strip(), status.lower(), context.strip(), decision.strip(), consequences.strip(), tags_json, now),
        )
        self.conn.commit()
        adr_id = cursor.lastrowid

        record = ADRRecord(
            id=adr_id,
            title=title,
            status=status,
            context=context,
            decision=decision,
            consequences=consequences,
            tags=tags or [],
            created_at=now,
        )
        return {"status": "created", "adr_id": adr_id, "record": record.to_dict()}

    def list_adrs(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        """List all architecture decision records, optionally filtered by status."""
        cursor = self.conn.cursor()
        if status:
            cursor.execute("SELECT id, title, status, context, decision, consequences, tags, created_at FROM adr_records WHERE status = ? ORDER BY id ASC", (status.lower(),))
        else:
            cursor.execute("SELECT id, title, status, context, decision, consequences, tags, created_at FROM adr_records ORDER BY id ASC")
        rows = cursor.fetchall()
        results = []
        for r in rows:
            record = ADRRecord(
                id=r[0],
                title=r[1],
                status=r[2],
                context=r[3],
                decision=r[4],
                consequences=r[5],
                tags=json.loads(r[6]) if r[6] else [],
                created_at=r[7],
            )
            results.append(record.to_dict())
        return results

    def get_adr(self, adr_id: int) -> Optional[dict[str, Any]]:
        """Retrieve a specific ADR by its ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, title, status, context, decision, consequences, tags, created_at FROM adr_records WHERE id = ?", (adr_id,))
        row = cursor.fetchone()
        if not row:
            return None
        record = ADRRecord(
            id=row[0],
            title=row[1],
            status=row[2],
            context=row[3],
            decision=row[4],
            consequences=row[5],
            tags=json.loads(row[6]) if row[6] else [],
            created_at=row[7],
        )
        d = record.to_dict()
        d["markdown"] = record.to_markdown()
        return d


adr_manager = ADRManager()


@tool
def record_architecture_decision(
    title: str, context: str, decision: str, consequences: str, tags: list[str] = None
) -> dict[str, Any]:
    """Record an Architecture Decision Record (ADR) for system designs and technology choices.

    Args:
        title: Short title of the decision.
        context: The situation, problem, and constraints leading to the decision.
        decision: The chosen solution or architecture change.
        consequences: Positive, negative, or neutral outcomes of this decision.
        tags: Optional category tags.
    """
    return adr_manager.create_adr(
        title=title, context=context, decision=decision, consequences=consequences, tags=tags or []
    )
