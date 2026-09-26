"""Long-term memory subsystem.

Provides semantic and structured memory persistence across conversations,
with thread/user scoped namespaces, categorizations, and safety boundaries.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from langchain_core.tools import tool

DB_PATH = "chatbot.db"


def _get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS long_term_memories (
            id TEXT PRIMARY KEY,
            namespace TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memories_ns ON long_term_memories (namespace, category)"
    )
    conn.commit()
    return conn


class MemoryStore:
    """Manages persistent memory items partitioned by namespace."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.conn = _get_connection(db_path)

    def store(
        self,
        content: str,
        category: str = "fact",
        namespace: str = "global",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Store a fact, preference, decision, or user constraint."""
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Memory content cannot be empty.")
        if len(clean_content) > 5000:
            clean_content = clean_content[:5000]

        mem_id = str(uuid.uuid4())
        clean_category = (category or "fact").strip().lower()[:50]
        clean_ns = (namespace or "global").strip()[:100]
        meta_json = json.dumps(metadata or {})

        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO long_term_memories (id, namespace, category, content, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (mem_id, clean_ns, clean_category, clean_content, meta_json, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()
        return {
            "id": mem_id,
            "namespace": clean_ns,
            "category": clean_category,
            "content": clean_content,
            "status": "stored",
        }

    def retrieve(
        self,
        query: str,
        namespace: str = "global",
        category: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve memories matching query tokens within a namespace."""
        cursor = self.conn.cursor()
        clean_ns = (namespace or "global").strip()[:100]

        if category:
            cursor.execute(
                "SELECT id, namespace, category, content, metadata, created_at "
                "FROM long_term_memories WHERE namespace = ? AND category = ? "
                "ORDER BY created_at DESC",
                (clean_ns, category.strip().lower()),
            )
        else:
            cursor.execute(
                "SELECT id, namespace, category, content, metadata, created_at "
                "FROM long_term_memories WHERE namespace = ? "
                "ORDER BY created_at DESC",
                (clean_ns,),
            )
        rows = cursor.fetchall()
        if not rows:
            return []

        # Token-based relevance scoring
        query_tokens = set(query.lower().split()) if query else set()
        scored: list[tuple[float, dict[str, Any]]] = []

        for row in rows:
            mem_id, ns, cat, content, meta_str, created_at = row
            content_lower = content.lower()
            if query_tokens:
                matches = sum(1 for tok in query_tokens if tok in content_lower)
                score = matches / len(query_tokens)
            else:
                score = 1.0

            scored.append(
                (
                    score,
                    {
                        "id": mem_id,
                        "namespace": ns,
                        "category": cat,
                        "content": content,
                        "metadata": json.loads(meta_str) if meta_str else {},
                        "created_at": created_at,
                        "relevance": round(score, 3),
                    },
                )
            )

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[: max(1, limit)]]

    def delete(self, memory_id: str) -> bool:
        """Delete a memory item by ID."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM long_term_memories WHERE id = ?", (memory_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def list_all(self, namespace: str = "global", limit: int = 50) -> list[dict[str, Any]]:
        """List recent memories in a namespace."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, namespace, category, content, metadata, created_at "
            "FROM long_term_memories WHERE namespace = ? ORDER BY created_at DESC LIMIT ?",
            (namespace, limit),
        )
        return [
            {
                "id": r[0],
                "namespace": r[1],
                "category": r[2],
                "content": r[3],
                "metadata": json.loads(r[4]) if r[4] else {},
                "created_at": r[5],
            }
            for r in cursor.fetchall()
        ]


_memory_store = MemoryStore()


@tool
def store_memory(content: str, category: str = "fact", namespace: str = "global") -> dict[str, Any]:
    """Store an important fact, user preference, instruction, or key decision in long-term memory.

    Args:
        content: The text content to remember.
        category: Memory type ('preference', 'fact', 'decision', 'goal').
        namespace: Isolation scope (e.g. 'global' or 'thread:{thread_id}').
    """
    try:
        return _memory_store.store(content=content, category=category, namespace=namespace)
    except Exception as exc:
        return {"error": str(exc), "status": "failed"}


@tool
def retrieve_memory(query: str, namespace: str = "global", limit: int = 5) -> list[dict[str, Any]]:
    """Retrieve relevant facts, preferences, or decisions from long-term memory.

    Args:
        query: Search keywords or question.
        namespace: Memory isolation namespace (defaults to 'global').
        limit: Maximum number of memories to return (1-10).
    """
    try:
        return _memory_store.retrieve(query=query, namespace=namespace, limit=limit)
    except Exception as exc:
        return [{"error": str(exc)}]


@tool
def delete_memory(memory_id: str) -> dict[str, Any]:
    """Delete a memory item from long-term memory by ID.

    Args:
        memory_id: The unique ID of the memory item to delete.
    """
    try:
        success = _memory_store.delete(memory_id=memory_id)
        return {"id": memory_id, "deleted": success, "status": "success" if success else "not_found"}
    except Exception as exc:
        return {"id": memory_id, "error": str(exc), "status": "failed"}

