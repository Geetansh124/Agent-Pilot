"""Shadow evaluation comparator for LangGraph vs DeepSeek Harness parity."""
from __future__ import annotations

import logging
import math
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("harness.shadow")

_SECRET_PATTERN = re.compile(r"(nvapi-[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]+|Bearer\s+[A-Za-z0-9._-]+)", re.IGNORECASE)


@dataclass
class ShadowTurnMetrics:
    prompt_id: str
    tools_langgraph: list[str]
    tools_harness: list[str]
    tools_match: bool
    tokens_langgraph: int
    tokens_harness: int
    token_diff: int
    lg_latency_s: float
    harness_latency_s: float
    safety_violation: bool


class ShadowComparator:
    """Thread-safe comparator accumulating aggregate parity metrics between LangGraph and Harness."""

    def __init__(self):
        self._lock = threading.Lock()
        self.turns: list[ShadowTurnMetrics] = []

    def record_turn(
        self,
        prompt_id: str,
        langgraph_events: list[dict[str, Any]],
        harness_events: list[dict[str, Any]],
        lg_latency_s: float,
        harness_latency_s: float,
    ) -> ShadowTurnMetrics:
        """Compare a turn between LangGraph and Harness and record aggregate metrics."""
        tools_lg = [e["name"] for e in langgraph_events if e.get("type") == "tool" and "name" in e]
        tools_harness = [e["name"] for e in harness_events if e.get("type") == "tool" and "name" in e]

        tokens_lg = sum(len(e.get("content", "").split()) for e in langgraph_events if e.get("type") == "token")
        tokens_harness = sum(len(e.get("content", "").split()) for e in harness_events if e.get("type") == "token")

        tools_match = set(tools_lg) == set(tools_harness)

        # Safety check: scan all harness token/error text for unredacted secrets
        safety_violation = False
        for e in harness_events:
            text = str(e.get("content", "")) + " " + str(e.get("message", ""))
            if _SECRET_PATTERN.search(text):
                safety_violation = True
                break

        metric = ShadowTurnMetrics(
            prompt_id=prompt_id,
            tools_langgraph=tools_lg,
            tools_harness=tools_harness,
            tools_match=tools_match,
            tokens_langgraph=tokens_lg,
            tokens_harness=tokens_harness,
            token_diff=abs(tokens_lg - tokens_harness),
            lg_latency_s=lg_latency_s,
            harness_latency_s=harness_latency_s,
            safety_violation=safety_violation,
        )

        with self._lock:
            self.turns.append(metric)

        return metric

    def get_aggregate_summary(self) -> dict[str, Any]:
        """Compute aggregate parity summary. Contains NO PII or prompt text."""
        with self._lock:
            total = len(self.turns)
            if total == 0:
                return {
                    "total_turns": 0,
                    "tool_parity_pct": 100.0,
                    "avg_token_diff": 0.0,
                    "p95_lg_latency_s": 0.0,
                    "p95_harness_latency_s": 0.0,
                    "latency_overhead_pct": 0.0,
                    "safety_violations": 0,
                    "passed_promotion_criteria": True,
                }

            matching_tools = sum(1 for t in self.turns if t.tools_match)
            tool_parity_pct = (matching_tools / total) * 100.0

            avg_token_diff = sum(t.token_diff for t in self.turns) / total

            lg_lats = sorted(t.lg_latency_s for t in self.turns)
            harness_lats = sorted(t.harness_latency_s for t in self.turns)

            idx_p95 = min(int(math.ceil(0.95 * total)) - 1, total - 1)
            p95_lg = lg_lats[idx_p95]
            p95_harness = harness_lats[idx_p95]

            latency_overhead_pct = (
                ((p95_harness - p95_lg) / p95_lg * 100.0) if p95_lg > 0 else 0.0
            )

            safety_violations = sum(1 for t in self.turns if t.safety_violation)

            passed_promotion = (
                tool_parity_pct >= 95.0
                and safety_violations == 0
                and latency_overhead_pct <= 25.0
            )

            return {
                "total_turns": total,
                "tool_parity_pct": round(tool_parity_pct, 2),
                "avg_token_diff": round(avg_token_diff, 2),
                "p95_lg_latency_s": round(p95_lg, 4),
                "p95_harness_latency_s": round(p95_harness, 4),
                "latency_overhead_pct": round(latency_overhead_pct, 2),
                "safety_violations": safety_violations,
                "passed_promotion_criteria": passed_promotion,
            }

    def reset(self) -> None:
        with self._lock:
            self.turns.clear()


_global_comparator = ShadowComparator()


def get_shadow_comparator() -> ShadowComparator:
    return _global_comparator

