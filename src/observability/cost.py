"""Token budgeting and cost tracking subsystem.

Monitors token consumption across user sessions, estimates dollar cost
based on model pricing tiers, and enforces budget caps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Default model pricing per 1 Million tokens (USD)
MODEL_PRICING = {
    "default": {"input_per_m": 0.20, "output_per_m": 0.80},
    "nemotron": {"input_per_m": 0.15, "output_per_m": 0.60},
    "gpt-4o": {"input_per_m": 2.50, "output_per_m": 10.00},
}


def estimate_token_count(text: str) -> int:
    """Fast approximation of token count (average ~4 chars per token)."""
    clean = text.strip()
    if not clean:
        return 0
    return max(1, len(clean) // 4)


def calculate_cost(
    prompt_tokens: int, completion_tokens: int, model: str = "default"
) -> float:
    """Calculate USD cost for prompt and completion token counts."""
    tier = MODEL_PRICING.get(model, MODEL_PRICING["default"])
    input_cost = (prompt_tokens / 1_000_000.0) * tier["input_per_m"]
    output_cost = (completion_tokens / 1_000_000.0) * tier["output_per_m"]
    return round(input_cost + output_cost, 6)


class CostTracker:
    """Tracks token consumption and enforces budget caps per thread and globally."""

    def __init__(self, max_tokens_per_request: int = 16384, max_budget_usd: float = 50.0):
        self.max_tokens_per_request = max_tokens_per_request
        self.max_budget_usd = max_budget_usd
        self._thread_usage: dict[str, dict[str, Any]] = {}
        self.total_tokens_consumed = 0
        self.total_usd_spent = 0.0

    def check_request_budget(self, estimated_prompt_tokens: int) -> tuple[bool, str]:
        """Verify prompt does not exceed request token limits or total budget."""
        if estimated_prompt_tokens > self.max_tokens_per_request:
            return False, f"Request prompt ({estimated_prompt_tokens} tokens) exceeds limit of {self.max_tokens_per_request}."
        if self.total_usd_spent >= self.max_budget_usd:
            return False, f"Total account spending limit (${self.max_budget_usd:.2f}) reached."
        return True, ""

    def record_usage(
        self,
        thread_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "default",
    ) -> dict[str, Any]:
        """Log token usage and update cumulative spending figures."""
        cost = calculate_cost(prompt_tokens, completion_tokens, model)
        total_tokens = prompt_tokens + completion_tokens

        self.total_tokens_consumed += total_tokens
        self.total_usd_spent = round(self.total_usd_spent + cost, 6)

        tid = thread_id or "global"
        if tid not in self._thread_usage:
            self._thread_usage[tid] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
            }

        t_entry = self._thread_usage[tid]
        t_entry["prompt_tokens"] += prompt_tokens
        t_entry["completion_tokens"] += completion_tokens
        t_entry["total_tokens"] += total_tokens
        t_entry["total_cost_usd"] = round(t_entry["total_cost_usd"] + cost, 6)

        return {
            "thread_id": tid,
            "request_tokens": total_tokens,
            "request_cost_usd": cost,
            "thread_total_tokens": t_entry["total_tokens"],
            "thread_total_cost": t_entry["total_cost_usd"],
            "global_total_cost": self.total_usd_spent,
        }

    def get_summary(self, thread_id: str | None = None) -> dict[str, Any]:
        """Return usage summary."""
        if thread_id and thread_id in self._thread_usage:
            return {
                "thread_id": thread_id,
                **self._thread_usage[thread_id],
                "global_usd_spent": self.total_usd_spent,
            }
        return {
            "total_tokens_consumed": self.total_tokens_consumed,
            "total_usd_spent": self.total_usd_spent,
            "active_threads": len(self._thread_usage),
        }


cost_tracker = CostTracker()
