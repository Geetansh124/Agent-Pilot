"""Agent services, automation, observability, voice, and HITL API router."""
from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.agent.hitl import hitl_manager
from src.observability.audit import audit_logger
from src.observability.cost import cost_tracker

services_router = APIRouter()


# ---------------------------------------------------------------------------
# Human-in-the-Loop & Observability Endpoints
# ---------------------------------------------------------------------------
@services_router.get("/hitl/pending")
def list_pending_approvals(thread_id: Optional[str] = None) -> list[dict[str, Any]]:
    """List pending human-in-the-loop tool approvals."""
    return hitl_manager.get_pending(thread_id=thread_id)


@services_router.post("/hitl/{request_id}/approve")
def approve_hitl_action(request_id: str) -> dict[str, Any]:
    """Approve a paused sensitive action."""
    success = hitl_manager.approve(request_id)
    if not success:
        raise HTTPException(status_code=404, detail="Request not found or not in pending state.")
    audit_logger.log("hitl_approval", f"Approved {request_id}", status="approved")
    return {"request_id": request_id, "status": "approved"}


@services_router.post("/hitl/{request_id}/reject")
def reject_hitl_action(request_id: str, reason: str = "User declined") -> dict[str, Any]:
    """Reject a paused sensitive action."""
    success = hitl_manager.reject(request_id, reason=reason)
    if not success:
        raise HTTPException(status_code=404, detail="Request not found or not in pending state.")
    audit_logger.log("hitl_rejection", f"Rejected {request_id}: {reason}", status="rejected")
    return {"request_id": request_id, "status": "rejected", "reason": reason}


@services_router.get("/observability/audit")
def get_audit_records(thread_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    """Query recent audit events for compliance."""
    return audit_logger.query(thread_id=thread_id, limit=limit)


@services_router.get("/observability/usage")
def get_usage_metrics(thread_id: Optional[str] = None) -> dict[str, Any]:
    """Get token consumption and cost metrics."""
    return cost_tracker.get_summary(thread_id=thread_id)


# ---------------------------------------------------------------------------
# Graph, Automation, Voice & Critic Endpoints
# ---------------------------------------------------------------------------
@services_router.get("/graph/{entity}")
def query_graph_endpoint(entity: str) -> dict[str, Any]:
    """Retrieve connected knowledge graph nodes and relations for an entity."""
    from src.graph import knowledge_graph
    return knowledge_graph.query_subgraph(entity=entity)


class ScheduleTaskRequest(BaseModel):
    name: str
    interval_seconds: int = 3600
    payload: Optional[dict[str, Any]] = None


@services_router.post("/automation/schedule")
def schedule_task_endpoint(req: ScheduleTaskRequest) -> dict[str, Any]:
    """Schedule a recurring background task."""
    from src.automation import task_scheduler
    task = task_scheduler.schedule(req.name, req.interval_seconds, req.payload)
    return task.to_dict()


@services_router.get("/automation/tasks")
def list_tasks_endpoint() -> list[dict[str, Any]]:
    """List scheduled background tasks."""
    from src.automation import task_scheduler
    return task_scheduler.list_tasks()


class WorkflowRunRequest(BaseModel):
    name: str
    steps: list[dict[str, Any]]
    context: Optional[dict[str, Any]] = None


@services_router.post("/automation/workflow")
def run_workflow_endpoint(req: WorkflowRunRequest) -> dict[str, Any]:
    """Execute an autonomous multi-step workflow."""
    from src.automation import workflow_runner
    return workflow_runner.run_workflow(req.name, req.steps, req.context)


@services_router.post("/voice/transcribe")
async def voice_transcribe_endpoint(file: UploadFile = File(...)) -> dict[str, Any]:
    """Transcribe user audio stream into text."""
    from src.voice import audio_processor
    data = await file.read()
    return audio_processor.transcribe(data, filename=file.filename or "audio.wav")


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "en-US-Neural"
    speed: float = 1.0


@services_router.post("/voice/synthesize")
def voice_synthesize_endpoint(req: SynthesizeRequest) -> dict[str, Any]:
    """Synthesize text into streamable audio."""
    from src.voice import audio_processor
    return audio_processor.synthesize(req.text, voice=req.voice, speed=req.speed)


class CritiqueRequest(BaseModel):
    question: str
    context: str
    response: str


@services_router.post("/agent/critique")
def critique_response_endpoint(req: CritiqueRequest) -> dict[str, Any]:
    """Critique an assistant answer against reference context."""
    from src.agent import critic_agent
    return critic_agent.evaluate(req.question, req.context, req.response)
