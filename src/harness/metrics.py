"""Observability, per-tenant token/cost accounting, and quota enforcement for DeepSeek Harness."""
from __future__ import annotations

import logging
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from src.harness.config import HarnessSettings, get_harness_settings
from src.harness.errors import QuotaExceeded
from src.observability import audit_logger

logger = logging.getLogger("harness.metrics")

# Model pricing tiers per 1 Million tokens (USD)
HARNESS_MODEL_PRICING: dict[str, dict[str, float]] = {
    "default": {"input_per_m": 0.14, "output_per_m": 0.28},
    "deepseek": {"input_per_m": 0.14, "output_per_m": 0.28},
    "nvidia/nemotron-3-ultra-550b-a55b": {"input_per_m": 0.15, "output_per_m": 0.60},
}


def calculate_harness_cost(prompt_tokens: int, completion_tokens: int, model: str = "default") -> float:
    """Calculate estimated cost in USD based on model pricing."""
    tier = HARNESS_MODEL_PRICING.get(model, HARNESS_MODEL_PRICING["default"])
    cost = (prompt_tokens / 1_000_000.0) * tier["input_per_m"] + (
        completion_tokens / 1_000_000.0
    ) * tier["output_per_m"]
    return round(cost, 6)


@dataclass
class TenantMetrics:
    tenant_id: str
    total_turns: int = 0
    active_turns: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    tool_calls_count: int = 0
    approvals_count: int = 0
    fallbacks_count: int = 0
    quota_violations: int = 0


class HarnessMetricsTracker:
    """Thread-safe collector for per-tenant quotas, token tracking, and structured audit events."""

    def __init__(self):
        self._lock = threading.Lock()
        self._tenants: dict[str, TenantMetrics] = {}
        self._thread_active_tools: dict[str, int] = {}

    def _get_or_create(self, tenant_id: str) -> TenantMetrics:
        if tenant_id not in self._tenants:
            self._tenants[tenant_id] = TenantMetrics(tenant_id=tenant_id)
        return self._tenants[tenant_id]

    def start_turn(
        self,
        tenant_id: str,
        thread_id: str,
        settings: Optional[HarnessSettings] = None,
    ) -> None:
        """Enforce concurrency quotas and log audit turn start."""
        cfg = settings or get_harness_settings()
        with self._lock:
            tenant = self._get_or_create(tenant_id)
            if tenant.active_turns >= cfg.max_concurrent_turns:
                tenant.quota_violations += 1
                audit_logger.log(
                    "harness_quota_exceeded",
                    f"Concurrency limit ({cfg.max_concurrent_turns}) exceeded for tenant {tenant_id}",
                    thread_id,
                    status="warning",
                    details={"tenant_id": tenant_id, "active_turns": tenant.active_turns},
                )
                raise QuotaExceeded(
                    f"Maximum concurrent turns ({cfg.max_concurrent_turns}) exceeded for tenant. Retry later."
                )

            tenant.active_turns += 1
            tenant.total_turns += 1
            self._thread_active_tools[thread_id] = 0

        audit_logger.log(
            "harness_turn_start",
            f"Started turn for thread {thread_id}",
            thread_id,
            status="info",
            details={"tenant_id": tenant_id, "model": cfg.model},
        )

    def end_turn(
        self,
        tenant_id: str,
        thread_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "default",
    ) -> dict[str, Any]:
        """Record token accounting, compute cost, decrement active turns, and emit audit turn end."""
        cost = calculate_harness_cost(prompt_tokens, completion_tokens, model)
        total_tokens = prompt_tokens + completion_tokens

        with self._lock:
            tenant = self._get_or_create(tenant_id)
            tenant.active_turns = max(0, tenant.active_turns - 1)
            tenant.prompt_tokens += prompt_tokens
            tenant.completion_tokens += completion_tokens
            tenant.total_tokens += total_tokens
            tenant.total_cost_usd = round(tenant.total_cost_usd + cost, 6)
            self._thread_active_tools.pop(thread_id, None)

        audit_logger.log(
            "harness_turn_end",
            f"Completed turn for thread {thread_id}",
            thread_id,
            status="info",
            details={
                "tenant_id": tenant_id,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_usd": cost,
            },
        )

        return {
            "tenant_id": tenant_id,
            "thread_id": thread_id,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost,
        }

    def record_tool_call(
        self,
        tenant_id: str,
        thread_id: str,
        tool_name: str,
        settings: Optional[HarnessSettings] = None,
    ) -> None:
        """Track tool calls per turn and enforce max_tool_calls quota."""
        cfg = settings or get_harness_settings()
        with self._lock:
            tenant = self._get_or_create(tenant_id)
            tenant.tool_calls_count += 1
            count = self._thread_active_tools.get(thread_id, 0) + 1
            self._thread_active_tools[thread_id] = count

            if count > cfg.max_tool_calls:
                tenant.quota_violations += 1
                audit_logger.log(
                    "harness_quota_exceeded",
                    f"Max tool calls quota ({cfg.max_tool_calls}) exceeded on thread {thread_id}",
                    thread_id,
                    status="warning",
                    details={"tool_name": tool_name, "count": count},
                )
                raise QuotaExceeded(
                    f"Tool calls per turn limit ({cfg.max_tool_calls}) exceeded on thread {thread_id}."
                )

        audit_logger.log(
            "harness_tool_call",
            f"Tool invoked: {tool_name}",
            thread_id,
            status="info",
            details={"tenant_id": tenant_id, "tool_name": tool_name},
        )

    def record_approval(self, tenant_id: str, thread_id: str, tool_name: str, decision: str) -> None:
        """Record approval audit event and increment approval count."""
        with self._lock:
            tenant = self._get_or_create(tenant_id)
            tenant.approvals_count += 1

        audit_logger.log(
            "harness_approval",
            f"Approval {decision} for tool {tool_name}",
            thread_id,
            status="info",
            details={"tenant_id": tenant_id, "tool_name": tool_name, "decision": decision},
        )

    def record_fallback(self, tenant_id: str, thread_id: str, reason: str) -> None:
        """Record fallback audit event and increment fallback counter."""
        with self._lock:
            tenant = self._get_or_create(tenant_id)
            tenant.fallbacks_count += 1

        audit_logger.log(
            "harness_fallback",
            f"Fallback to LangGraph: {reason}",
            thread_id,
            status="warning",
            details={"tenant_id": tenant_id, "reason": reason},
        )

    def get_summary(self, tenant_id: Optional[str] = None) -> dict[str, Any]:
        """Produce aggregate and per-tenant metrics summary snapshot."""
        with self._lock:
            if tenant_id:
                tenant = self._get_or_create(tenant_id)
                return {"tenant": asdict(tenant)}

            all_tenants = {k: asdict(v) for k, v in self._tenants.items()}
            total_turns = sum(t.total_turns for t in self._tenants.values())
            total_tokens = sum(t.total_tokens for t in self._tenants.values())
            total_cost = round(sum(t.total_cost_usd for t in self._tenants.values()), 6)
            total_tool_calls = sum(t.tool_calls_count for t in self._tenants.values())
            total_violations = sum(t.quota_violations for t in self._tenants.values())

            return {
                "tenants": all_tenants,
                "tenant_count": len(all_tenants),
                "total_turns": total_turns,
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost,
                "total_tool_calls": total_tool_calls,
                "total_quota_violations": total_violations,
            }

    def reset(self) -> None:
        with self._lock:
            self._tenants.clear()
            self._thread_active_tools.clear()


_global_tracker = HarnessMetricsTracker()


def get_metrics_tracker() -> HarnessMetricsTracker:
    return _global_tracker

