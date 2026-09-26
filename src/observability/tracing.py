"""Structured OpenTelemetry-compatible distributed tracing for multi-agent workflows.

Tracks execution spans across supervisor, swarm agents, subagents, and tools
with parent-child hierarchy, duration metrics, attributes, and OTLP-like export.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    parent_span_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    status: str = "UNSET"  # OK, ERROR, UNSET
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        self.events.append({
            "name": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attributes": attributes or {},
        })

    def finish(self, status: str = "OK", error: Optional[str] = None) -> None:
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.status = status
        if error:
            self.status = "ERROR"
            self.set_attribute("error.message", error)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentTracer:
    """In-memory distributed tracer managing trace contexts and spans."""

    def __init__(self):
        self._spans: dict[str, list[Span]] = {}  # trace_id -> list of Spans

    def start_trace(self, root_name: str, attributes: Optional[dict[str, Any]] = None) -> Span:
        """Start a new root trace and return the root span."""
        trace_id = str(uuid.uuid4()).replace("-", "")
        root_span = Span(
            name=root_name,
            trace_id=trace_id,
            parent_span_id=None,
            attributes=attributes or {},
        )
        self._spans[trace_id] = [root_span]
        return root_span

    def start_span(
        self,
        name: str,
        trace_id: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Span:
        """Create a child span within an existing trace."""
        span = Span(
            name=name,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            attributes=attributes or {},
        )
        if trace_id not in self._spans:
            self._spans[trace_id] = []
        self._spans[trace_id].append(span)
        return span

    def get_trace(self, trace_id: str) -> list[dict[str, Any]]:
        """Retrieve all spans for a specific trace ordered by start time."""
        spans = self._spans.get(trace_id, [])
        return [s.to_dict() for s in sorted(spans, key=lambda x: x.start_time)]

    def export_trace_summary(self, trace_id: str) -> dict[str, Any]:
        """Generate a hierarchical trace summary with aggregate statistics."""
        spans = self._spans.get(trace_id, [])
        if not spans:
            return {"error": f"Trace {trace_id} not found."}

        total_duration = sum(s.duration_ms for s in spans)
        errors = [s.name for s in spans if s.status == "ERROR"]

        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "total_duration_ms": round(total_duration, 2),
            "has_errors": len(errors) > 0,
            "error_spans": errors,
            "spans": [s.to_dict() for s in spans],
        }


agent_tracer = AgentTracer()
