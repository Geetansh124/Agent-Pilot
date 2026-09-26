"""Human-in-the-Loop (HITL) approval gates.

Prevents unauthorized destructive actions (file writes, file deletions, external API mutations)
by requiring explicit user confirmation before tool execution.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

SENSITIVE_TOOLS = {
    "delete_workspace_file",
    "write_workspace_file",
    "call_api",
    "run_code_task",
}


@dataclass
class ApprovalRequest:
    request_id: str
    tool_name: str
    arguments: dict[str, Any]
    thread_id: str
    status: str = "pending"  # pending, approved, rejected
    reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HITLManager:
    """Manages pending and resolved tool approval requests."""

    def __init__(self, auto_approve: bool = False):
        self._requests: dict[str, ApprovalRequest] = {}
        self.auto_approve = auto_approve

    def is_sensitive(self, tool_name: str) -> bool:
        """Check if tool requires human authorization."""
        return tool_name in SENSITIVE_TOOLS

    def request_approval(
        self, tool_name: str, arguments: dict[str, Any], thread_id: str = "global"
    ) -> ApprovalRequest:
        """Create a new approval gate request."""
        req_id = str(uuid.uuid4())[:8]
        req = ApprovalRequest(
            request_id=req_id,
            tool_name=tool_name,
            arguments=arguments,
            thread_id=thread_id,
            status="approved" if self.auto_approve else "pending",
        )
        self._requests[req_id] = req
        return req

    def approve(self, request_id: str) -> bool:
        """Approve a pending request."""
        req = self._requests.get(request_id)
        if req and req.status == "pending":
            req.status = "approved"
            return True
        return False

    def reject(self, request_id: str, reason: str = "Rejected by user") -> bool:
        """Reject a pending request."""
        req = self._requests.get(request_id)
        if req and req.status == "pending":
            req.status = "rejected"
            req.reason = reason
            return True
        return False

    def get_pending(self, thread_id: Optional[str] = None) -> list[dict[str, Any]]:
        """List all pending approval requests."""
        items = [
            req.to_dict()
            for req in self._requests.values()
            if req.status == "pending" and (not thread_id or req.thread_id == thread_id)
        ]
        return items

    def get_request(self, request_id: str) -> Optional[dict[str, Any]]:
        req = self._requests.get(request_id)
        return req.to_dict() if req else None


hitl_manager = HITLManager()
