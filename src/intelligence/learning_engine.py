"""Self-learning engine that extracts success/failure patterns from audit logs.

Tracks which tool sequences, agent delegations, and parameter choices lead to
successful outcomes, then exposes recommendations so the supervisor and planner
can automatically prefer proven strategies.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Optional


from langchain_core.tools import tool

DB_PATH = "chatbot.db"


def _get_learning_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS learning_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            avg_duration_ms REAL DEFAULT 0.0,
            last_used TIMESTAMP,
            confidence REAL DEFAULT 0.0,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(pattern_type, pattern_key)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pattern_type ON learning_patterns (pattern_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pattern_confidence ON learning_patterns (confidence DESC)"
    )
    conn.commit()
    return conn


class LearningEngine:
    """Extracts and learns from patterns in audit logs and task outcomes."""

    def __init__(self, db_path: str = DB_PATH, storage_path: Optional[str] = None):
        self.db_path = storage_path if storage_path is not None else db_path
        self.conn = _get_learning_conn(self.db_path)

    def record_outcome(
        self,
        pattern_type: str = "",
        pattern_key: str = "",
        success: bool = True,
        duration_ms: float = 0.0,
        metadata: Optional[dict[str, Any]] = None,
        task: str = "",
        chosen_agent: str = "",
        tools_used: Optional[list[str]] = None,
        feedback_score: float = 1.0,
    ) -> dict[str, Any]:
        """Record a success or failure for a specific pattern or task execution."""
        if task or chosen_agent:
            # Task-level outcome recording
            agent_str = chosen_agent or "general"
            key = f"{task[:30]}:{agent_str}"
            p_type = "agent_routing"
            meta = {"task": task, "tools": tools_used or [], "feedback": feedback_score}
            if tools_used:
                for tool_name in tools_used:
                    self.record_outcome("tool_sequence", tool_name, success, duration_ms)
            return self._record_single_outcome(p_type, key, success, duration_ms, meta)
        else:
            return self._record_single_outcome(
                pattern_type or "general", pattern_key or "default", success, duration_ms, metadata
            )

    def _record_single_outcome(
        self,
        pattern_type: str,
        pattern_key: str,
        success: bool,
        duration_ms: float = 0.0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """INSERT INTO learning_patterns (pattern_type, pattern_key, success_count,
               failure_count, avg_duration_ms, last_used, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(pattern_type, pattern_key) DO UPDATE SET
                 success_count = success_count + ?,
                 failure_count = failure_count + ?,
                 avg_duration_ms = (avg_duration_ms + ?) / 2.0,
                 last_used = ?,
                 metadata = COALESCE(?, metadata)""",
            (
                pattern_type, pattern_key,
                1 if success else 0,
                0 if success else 1,
                duration_ms, now,
                json.dumps(metadata or {}),
                1 if success else 0,
                0 if success else 1,
                duration_ms, now,
                json.dumps(metadata) if metadata else None,
            ),
        )

        cursor.execute(
            """UPDATE learning_patterns SET confidence =
               CASE WHEN (success_count + failure_count) > 0
               THEN CAST(success_count AS REAL) / (success_count + failure_count)
               ELSE 0.0 END
               WHERE pattern_type = ? AND pattern_key = ?""",
            (pattern_type, pattern_key),
        )
        self.conn.commit()

        return {
            "pattern_type": pattern_type,
            "pattern_key": pattern_key,
            "success": success,
            "recorded": True,
        }

    def get_learned_patterns(self) -> dict[str, Any]:
        """Return learned patterns organized by agent and tool profiles."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT pattern_type, pattern_key, success_count, failure_count, confidence, avg_duration_ms FROM learning_patterns"
        )
        rows = cursor.fetchall()
        agent_profiles = {}
        tool_profiles = {}
        for r in rows:
            ptype, pkey, succ, fail, conf, dur = r
            if ptype == "agent_routing":
                agent = pkey.split(":")[-1] if ":" in pkey else pkey
                agent_profiles[agent] = {
                    "success_count": succ,
                    "failure_count": fail,
                    "confidence": round(conf or 0, 3),
                    "avg_duration_ms": dur,
                }
            elif ptype == "tool_sequence":
                tool_profiles[pkey] = {
                    "success_count": succ,
                    "failure_count": fail,
                    "confidence": round(conf or 0, 3),
                }
        return {"agent_profiles": agent_profiles, "tool_profiles": tool_profiles, "total_patterns": len(rows)}

    def get_best_pattern(
        self,
        pattern_type: str,
        min_samples: int = 1,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Get the highest-confidence patterns for a given type."""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT pattern_key, success_count, failure_count,
                      avg_duration_ms, confidence, last_used, metadata
               FROM learning_patterns
               WHERE pattern_type = ?
                 AND (success_count + failure_count) >= ?
               ORDER BY confidence DESC, success_count DESC
               LIMIT ?""",
            (pattern_type, min_samples, limit),
        )
        rows = cursor.fetchall()
        return [
            {
                "pattern_key": r[0],
                "success_count": r[1],
                "failure_count": r[2],
                "avg_duration_ms": r[3],
                "confidence": round(r[4], 3),
                "last_used": r[5],
                "metadata": json.loads(r[6]) if r[6] else {},
            }
            for r in rows
        ]

    def recommend_agent(
        self, task_description: str = "", task: str = ""
    ) -> dict[str, Any]:
        """Recommend the best agent for a task based on learned patterns."""
        desc = task_description or task
        best = self.get_best_pattern("agent_routing", min_samples=1, limit=10)
        if not best:
            return {
                "recommendation": "auto",
                "recommended_agent": "auto",
                "confidence": 0.0,
                "reason": "No learned patterns yet.",
            }

        task_lower = desc.lower()

        scored: list[tuple[float, dict[str, Any]]] = []
        for pattern in best:
            key_terms = set(re.findall(r"\w+", pattern["pattern_key"].lower()))
            overlap = sum(1 for term in key_terms if term in task_lower)
            if overlap > 0:
                score = pattern["confidence"] * (overlap / max(len(key_terms), 1))
                scored.append((score, pattern))

        if not scored:
            # Default to top confident agent if any
            top = best[0]
        else:
            scored.sort(key=lambda x: x[0], reverse=True)
            top = scored[0][1]

        parts = top["pattern_key"].split(":")
        agent_role = parts[-1] if len(parts) > 1 else parts[0]

        return {
            "recommendation": agent_role,
            "recommended_agent": agent_role,
            "confidence": top["confidence"],
            "success_count": top["success_count"],
            "reason": f"Pattern '{top['pattern_key']}' has {top['confidence']:.0%} success rate.",
        }


    def recommend_tool_sequence(self, task_type: str) -> dict[str, Any]:
        """Recommend the best tool sequence for a given task type."""
        best = self.get_best_pattern("tool_sequence", min_samples=2, limit=3)
        matching = [p for p in best if task_type.lower() in p["pattern_key"].lower()]
        if matching:
            top = matching[0]
            return {
                "recommended_sequence": top["pattern_key"],
                "confidence": top["confidence"],
                "avg_duration_ms": top["avg_duration_ms"],
            }
        return {"recommended_sequence": None, "confidence": 0.0}

    def learn_from_audit(self, limit: int = 100) -> dict[str, Any]:
        """Scan recent audit logs and extract success/failure patterns."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                """SELECT event_type, action, status, duration_ms, details
                   FROM audit_logs
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            )
        except sqlite3.OperationalError:
            return {"patterns_extracted": 0, "reason": "audit_logs table not found"}

        rows = cursor.fetchall()
        patterns_found = 0

        for row in rows:
            event_type, action, status, duration_ms, details_str = row
            success = status.lower() in ("success", "completed", "ok")
            details = json.loads(details_str) if details_str else {}

            # Extract agent routing patterns
            if event_type in ("chat", "delegation"):
                agent = details.get("agent", details.get("assigned_agent", ""))
                if agent:
                    key = f"{action[:30]}:{agent}"
                    self.record_outcome("agent_routing", key, success, duration_ms or 0)
                    patterns_found += 1

            # Extract tool sequence patterns
            if event_type == "tool_call":
                tool_name = details.get("tool", action)
                self.record_outcome("tool_sequence", tool_name, success, duration_ms or 0)
                patterns_found += 1

        return {"patterns_extracted": patterns_found, "audit_rows_scanned": len(rows)}

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics of all learned patterns."""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT pattern_type, COUNT(*),
                      AVG(confidence), SUM(success_count), SUM(failure_count)
               FROM learning_patterns
               GROUP BY pattern_type"""
        )
        rows = cursor.fetchall()
        return {
            "pattern_types": {
                r[0]: {
                    "count": r[1],
                    "avg_confidence": round(r[2] or 0, 3),
                    "total_successes": r[3] or 0,
                    "total_failures": r[4] or 0,
                }
                for r in rows
            },
            "total_patterns": sum(r[1] for r in rows),
        }


learning_engine = LearningEngine()


@tool
def learn_from_history(limit: int = 100) -> dict[str, Any]:
    """Analyze recent audit logs to extract and learn success/failure patterns.

    Args:
        limit: Number of recent audit records to scan (default 100).
    """
    return learning_engine.learn_from_audit(limit=limit)


@tool
def get_learning_recommendation(
    task_description: str, recommendation_type: str = "agent"
) -> dict[str, Any]:
    """Get an AI-learned recommendation for the best agent or tool sequence.

    Args:
        task_description: The task or query to get a recommendation for.
        recommendation_type: 'agent' for best agent, 'tools' for best tool sequence.
    """
    if recommendation_type == "tools":
        return learning_engine.recommend_tool_sequence(task_description)
    return learning_engine.recommend_agent(task_description)


SelfLearningEngine = LearningEngine

