"""FastAPI router for Thread Approvals and Interactive Questions."""
from __future__ import annotations

from typing import Any, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.auth import get_current_user
from src.harness.approvals import DecisionConflict, get_approval_bridge
from src.storage.routes import _extract_user_id

approval_router = APIRouter(tags=["approvals"])


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["allowed-once", "rejected", "cancelled"]


class QuestionAnswerItem(BaseModel):
    id: str
    selected: list[str] = Field(default_factory=list)
    custom: Optional[str] = None


class QuestionAnswerRequest(BaseModel):
    answers: Optional[list[QuestionAnswerItem]] = None
    cancelled: bool = False


def _verify_thread_access(thread_id: str, user: dict[str, Any]) -> str:
    """Ensure user owns the thread; return user_id or raise 404."""
    from api_server import _user_owns_thread
    user_id = _extract_user_id(user)
    if not _user_owns_thread(thread_id, user_id, user.get("role", "user")):
        raise HTTPException(status_code=404, detail="Thread not found or access denied.")
    return user_id


@approval_router.get("/api/threads/{thread_id}/approvals")
def get_thread_approvals(
    thread_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve active pending approvals for a thread."""
    _verify_thread_access(thread_id, user)
    bridge = get_approval_bridge()
    pending = bridge.get_pending_approvals(thread_id)
    return {"thread_id": thread_id, "approvals": pending}


@approval_router.post("/api/threads/{thread_id}/approvals/{request_id}")
def submit_thread_approval(
    thread_id: str,
    request_id: str,
    body: ApprovalDecisionRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit a one-shot authorization decision for a pending tool call."""
    user_id = _verify_thread_access(thread_id, user)
    bridge = get_approval_bridge()
    try:
        record = bridge.submit_decision(
            request_id=request_id,
            thread_id=thread_id,
            decision=body.decision,
            decided_by=user_id,
        )
        return {"success": True, "approval": record}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Approval request '{request_id}' not found.")
    except DecisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@approval_router.post("/api/threads/{thread_id}/questions/{request_id}")
def submit_thread_question(
    thread_id: str,
    request_id: str,
    body: QuestionAnswerRequest,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit answers or cancellation for an interactive agent question."""
    _verify_thread_access(thread_id, user)
    bridge = get_approval_bridge()
    try:
        ans_dicts = [a.model_dump() for a in body.answers] if body.answers else None
        record = bridge.answer_question(
            question_id=request_id,
            thread_id=thread_id,
            answers=ans_dicts,
            cancelled=body.cancelled,
        )
        return {"success": True, "question": record}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Question '{request_id}' not found.")
    except DecisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@approval_router.get("/api/admin/metrics/harness")
def get_harness_admin_metrics(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve aggregate and per-tenant Harness metrics snapshot (Admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required.")
    from src.harness.metrics import get_metrics_tracker
    return get_metrics_tracker().get_summary()

