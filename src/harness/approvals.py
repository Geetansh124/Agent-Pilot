"""Human-in-the-Loop (HITL) approval and question bridge for DeepSeek Harness."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Literal, Optional

from src.agent.hitl import ApprovalRequest, HITLManager, hitl_manager
from src.observability import audit_logger

logger = logging.getLogger("harness.approvals")

DecisionType = Literal["allowed-once", "rejected", "cancelled"]


class DecisionConflict(Exception):
    """Raised when an approval request has already reached a terminal decision."""


class RequestExpired(Exception):
    """Raised when an approval or question request has expired."""


class ApprovalBridge:
    """Bridges harness approval and question events to Agent-Pilot HITLManager."""

    def __init__(self, manager: Optional[HITLManager] = None, default_timeout_s: float = 300.0):
        self.manager = manager or hitl_manager
        self.default_timeout_s = default_timeout_s
        self._decisions: dict[str, dict[str, Any]] = {}
        self._questions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get_pending_approvals(self, thread_id: str) -> list[dict[str, Any]]:
        """List active pending approvals for the specified thread."""
        with self._lock:
            pending = self.manager.get_pending(thread_id=thread_id)
            now = time.time()
            valid = []
            for item in pending:
                req_id = item.get("request_id", "")
                created = item.get("created_timestamp")
                if created is None and "created_at" in item:
                    try:
                        from datetime import datetime
                        created = datetime.fromisoformat(str(item["created_at"])).timestamp()
                    except Exception:
                        created = now
                if created is None:
                    created = now
                if (now - created) > self.default_timeout_s:
                    # Automatically fail-closed on expiration
                    self.manager.reject(req_id, reason="Approval request expired.")
                    audit_logger.log("harness_approval", "Approval expired; denied", thread_id, status="expired")
                else:
                    valid.append(item)
            return valid

    def submit_decision(
        self,
        request_id: str,
        thread_id: str,
        decision: DecisionType,
        decided_by: str = "user",
    ) -> dict[str, Any]:
        """Submit a one-shot decision for a pending approval request."""
        with self._lock:
            if request_id in self._decisions:
                raise DecisionConflict(f"Request '{request_id}' has already been decided.")

            req = self.manager.get_request(request_id)
            if not req:
                raise KeyError(f"Approval request '{request_id}' not found.")

            if req.get("status") != "pending":
                raise DecisionConflict(f"Request '{request_id}' is no longer pending.")

            if decision == "allowed-once":
                self.manager.approve(request_id)
                status_str = "approved"
            elif decision == "rejected":
                self.manager.reject(request_id, reason="Rejected by user")
                status_str = "rejected"
            elif decision == "cancelled":
                self.manager.reject(request_id, reason="Cancelled by user")
                status_str = "cancelled"
            else:
                raise ValueError(f"Invalid decision: {decision}")

            record = {
                "request_id": request_id,
                "thread_id": thread_id,
                "decision": decision,
                "decided_by": decided_by,
                "decided_at": time.time(),
            }
            self._decisions[request_id] = record
            audit_logger.log(
                "harness_approval",
                f"Approval decision: {decision}",
                thread_id,
                status=status_str,
                details={"request_id": request_id, "decided_by": decided_by},
            )
            return record

    def register_question(
        self,
        question_id: str,
        thread_id: str,
        prompt: str,
        options: Optional[list[str]] = None,
        allow_custom: bool = True,
    ) -> dict[str, Any]:
        """Register an interactive question for the user."""
        with self._lock:
            q = {
                "question_id": question_id,
                "thread_id": thread_id,
                "prompt": prompt,
                "options": options or [],
                "allow_custom": allow_custom,
                "status": "pending",
                "created_at": time.time(),
            }
            self._questions[question_id] = q
            return q

    def answer_question(
        self,
        question_id: str,
        thread_id: str,
        answers: Optional[list[dict[str, Any]]] = None,
        cancelled: bool = False,
    ) -> dict[str, Any]:
        """Submit user answers to an interactive question."""
        with self._lock:
            q = self._questions.get(question_id)
            if not q or q["thread_id"] != thread_id:
                raise KeyError(f"Question '{question_id}' not found for thread.")

            if q.get("status") != "pending":
                raise DecisionConflict(f"Question '{question_id}' is already answered.")

            q["status"] = "cancelled" if cancelled else "answered"
            q["answers"] = answers or []
            q["answered_at"] = time.time()
            return q


_bridge_instance: Optional[ApprovalBridge] = None


def get_approval_bridge() -> ApprovalBridge:
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = ApprovalBridge()
    return _bridge_instance

