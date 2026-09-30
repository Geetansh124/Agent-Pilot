from __future__ import annotations

import json
import os
import time
import uuid
from collections import defaultdict
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from storage import storage
from langraph_rag_backend import (
    chatbot,
    delete_thread,
    get_all_thread_titles,
    ingest_pdf,
    retrieve_all_threads,
    set_thread_title,
    thread_document_metadata,
)
from src.rag import multi_doc_manager
from src.auth import auth_router, create_access_token, decode_and_verify_token, get_current_user, init_auth_db
from src.security import sanitize_output, validate_input_prompt
from src.agent import hitl_manager
from src.observability import audit_logger, cost_tracker, estimate_token_count

app = FastAPI(title="Agent-Pilot API", version="1.1.0")
origins = [
    o.strip()
    for o in os.getenv(
        "FRONTEND_ORIGIN", "http://localhost:3000,http://localhost:3001"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------
_RATE_LIMITS: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60.0
_RATE_LIMIT_MAX_REQUESTS = 60


def _check_rate_limit(client_ip: str) -> None:
    now = time.time()
    recent = [t for t in _RATE_LIMITS[client_ip] if now - t < _RATE_LIMIT_WINDOW]
    if len(recent) >= _RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 60 requests per minute.",
            headers={"Retry-After": "60"},
        )
    recent.append(now)
    _RATE_LIMITS[client_ip] = recent


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    thread_id: str = Field(min_length=1, max_length=100)
    response_format: str | None = Field(default=None, max_length=20)


class UpdateThreadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class ChatResponse(BaseModel):
    thread_id: str
    message: str
    tools_used: list[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _messages(thread_id: str) -> list[dict[str, str]]:
    state = chatbot.get_state(config={"configurable": {"thread_id": thread_id}})
    result = []
    for message in state.values.get("messages", []):
        if isinstance(message, HumanMessage):
            result.append({"role": "user", "content": str(message.content)})
        elif isinstance(message, AIMessage) and message.content:
            result.append({"role": "assistant", "content": str(message.content)})
    return result


def _chat_config(thread_id: str, response_format: str | None = None) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
            "response_format": response_format or "text",
        },
        "metadata": {"thread_id": thread_id},
        "run_name": "chat_turn",
    }


# ---------------------------------------------------------------------------
# Storage & Database Synchronization Lifecycle
# ---------------------------------------------------------------------------
@app.on_event("startup")
def startup_storage_restore() -> None:
    """Restore SQLite database and long-term memory store from persistent storage on startup."""
    try:
        if hasattr(storage, "restore_database"):
            storage.restore_database("chatbot.db")
        if hasattr(storage, "restore_memory"):
            storage.restore_memory("memory.db")
    except Exception as exc:
        logger.warning("Startup storage restore encountered warning: %s", exc)
    try:
        init_auth_db("chatbot.db")
    except Exception as exc:
        logger.warning("Startup auth DB initialization encountered warning: %s", exc)


@app.on_event("shutdown")
def shutdown_storage_sync() -> None:
    """Sync latest SQLite database and long-term memory store to persistent storage on shutdown."""
    try:
        if hasattr(storage, "sync_database"):
            storage.sync_database("chatbot.db")
        if hasattr(storage, "sync_memory"):
            storage.sync_memory("memory.db")
    except Exception as exc:
        logger.warning("Shutdown storage sync encountered warning: %s", exc)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, Any]:
    storage_status = "disabled"
    if storage.enabled:
        try:
            storage_status = "connected" if storage.health_check() else "unhealthy"
        except Exception:
            storage_status = "error"
    return {
        "status": "ok",
        "storage": {
            "backend": getattr(storage, "backend_name", "unknown"),
            "status": storage_status,
        },
    }


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------
@app.get("/api/threads")
def threads() -> list[dict[str, Any]]:
    saved_titles = get_all_thread_titles()
    result = []
    for thread_id in reversed(retrieve_all_threads()):
        messages = _messages(thread_id)
        first = next((m["content"] for m in messages if m["role"] == "user"), "New chat")
        result.append({
            "id": thread_id,
            "title": saved_titles.get(thread_id) or " ".join(first.split())[:48],
            "messages": messages,
        })
    return result


@app.post("/api/threads")
def new_thread() -> dict[str, str]:
    return {"id": str(uuid.uuid4()), "title": "New chat"}


@app.get("/api/threads/{thread_id}")
def thread(thread_id: str) -> dict[str, Any]:
    return {
        "id": thread_id,
        "messages": _messages(thread_id),
        "document": thread_document_metadata(thread_id) or None,
    }


@app.patch("/api/threads/{thread_id}")
def update_thread(thread_id: str, body: UpdateThreadRequest) -> dict[str, Any]:
    clean_title = " ".join(body.title.split())
    if not clean_title:
        raise HTTPException(status_code=422, detail="Title cannot be empty.")
    if set_thread_title(thread_id, clean_title):
        if hasattr(storage, "sync_database"):
            try:
                storage.sync_database("chatbot.db")
            except Exception:
                pass
        return {"id": thread_id, "title": clean_title}
    raise HTTPException(status_code=500, detail="Failed to update thread title.")


@app.delete("/api/threads/{thread_id}")
def remove_thread(thread_id: str) -> dict[str, Any]:
    if delete_thread(thread_id):
        if hasattr(storage, "sync_database"):
            try:
                storage.sync_database("chatbot.db")
            except Exception:
                pass
        return {"deleted": True, "thread_id": thread_id}
    raise HTTPException(status_code=404, detail="Thread not found or already deleted.")


# ---------------------------------------------------------------------------
# Chat — batch (original, kept for backward compatibility)
# ---------------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest, req: Request, background_tasks: BackgroundTasks) -> ChatResponse:
    _check_rate_limit(req.client.host if req.client else "unknown")
    is_safe, reason = validate_input_prompt(request.message)
    if not is_safe:
        audit_logger.log("security_block", "Prompt injection blocked", request.thread_id, status="blocked", details={"reason": reason})
        raise HTTPException(status_code=400, detail=f"Input rejected by security guardrail: {reason}")

    prompt_toks = estimate_token_count(request.message)
    budget_ok, budget_err = cost_tracker.check_request_budget(prompt_toks)
    if not budget_ok:
        raise HTTPException(status_code=429, detail=budget_err)

    t0 = time.time()
    config = _chat_config(request.thread_id, request.response_format)
    parts: list[str] = []
    tools: list[str] = []
    try:
        for chunk, _ in chatbot.stream(
            {"messages": [HumanMessage(content=request.message)]},
            config=config,
            stream_mode="messages",
        ):
            if isinstance(chunk, ToolMessage):
                name = getattr(chunk, "name", None)
                if name and name not in tools:
                    tools.append(name)
            elif isinstance(chunk, AIMessage) and chunk.content:
                parts.append(str(chunk.content))
    except (RuntimeError, ValueError) as exc:
        audit_logger.log("chat_error", str(exc), request.thread_id, status="failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    final_msg = sanitize_output("".join(parts))
    dur_ms = (time.time() - t0) * 1000
    cost_tracker.record_usage(request.thread_id, prompt_toks, estimate_token_count(final_msg))
    audit_logger.log("chat_request", "POST /api/chat", request.thread_id, status="success", duration_ms=dur_ms, details={"tools_used": tools})

    if hasattr(storage, "sync_database"):
        background_tasks.add_task(storage.sync_database, "chatbot.db")

    return ChatResponse(
        thread_id=request.thread_id,
        message=final_msg,
        tools_used=tools,
    )


# ---------------------------------------------------------------------------
# Chat — SSE streaming (new)
# ---------------------------------------------------------------------------
@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest, req: Request) -> StreamingResponse:
    """Stream chat tokens as Server-Sent Events.

    Event types:
      - ``token``  — a content fragment from the assistant
      - ``tool``   — a tool was invoked (includes ``name``)
      - ``done``   — stream finished (includes ``tools_used``)
      - ``error``  — an error occurred (includes ``message``)
    """
    _check_rate_limit(req.client.host if req.client else "unknown")
    is_safe, reason = validate_input_prompt(request.message)
    if not is_safe:
        audit_logger.log("security_block", "Prompt injection blocked", request.thread_id, status="blocked", details={"reason": reason})
        raise HTTPException(status_code=400, detail=f"Input rejected by security guardrail: {reason}")

    prompt_toks = estimate_token_count(request.message)
    budget_ok, budget_err = cost_tracker.check_request_budget(prompt_toks)
    if not budget_ok:
        raise HTTPException(status_code=429, detail=budget_err)

    def _event(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    def event_generator():
        config = _chat_config(request.thread_id, request.response_format)
        tools_used: list[str] = []
        collected_tokens: list[str] = []
        try:
            for chunk, _ in chatbot.stream(
                {"messages": [HumanMessage(content=request.message)]},
                config=config,
                stream_mode="messages",
            ):
                if isinstance(chunk, ToolMessage):
                    name = getattr(chunk, "name", None)
                    if name and name not in tools_used:
                        tools_used.append(name)
                        yield _event({"type": "tool", "name": name})
                elif isinstance(chunk, AIMessage) and chunk.content:
                    tok = sanitize_output(str(chunk.content))
                    collected_tokens.append(tok)
                    yield _event({"type": "token", "content": tok})
            cost_tracker.record_usage(request.thread_id, prompt_toks, estimate_token_count("".join(collected_tokens)))
            audit_logger.log("chat_stream", "POST /api/chat/stream", request.thread_id, status="success", details={"tools": tools_used})
            if hasattr(storage, "sync_database"):
                try:
                    storage.sync_database("chatbot.db")
                except Exception:
                    pass
            yield _event({"type": "done", "tools_used": tools_used})
        except (RuntimeError, ValueError) as exc:
            yield _event({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Document upload
# ---------------------------------------------------------------------------
@app.post("/api/threads/{thread_id}/document")
async def upload_document(
    thread_id: str, file: UploadFile = File(...)
) -> dict[str, Any]:
    filename = file.filename or "document.pdf"
    supported_exts = (".pdf", ".docx", ".doc", ".txt", ".md", ".markdown", ".csv", ".json")
    has_valid_ext = any(filename.lower().endswith(ext) for ext in supported_exts)
    allowed_content_types = {
        "application/pdf",
        "application/x-pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/csv",
        "application/json",
    }
    is_supported = has_valid_ext or ("." not in filename and file.content_type in allowed_content_types)
    if not is_supported:
        raise HTTPException(
            status_code=415,
            detail="Unsupported format. Supported: PDF, DOCX, CSV, TXT, Markdown, JSON.",
        )
    data = await file.read()
    if len(data) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds the 200 MB limit.")
    try:
        res = ingest_pdf(data, thread_id=thread_id, filename=filename)
        if hasattr(storage, "sync_database"):
            try:
                storage.sync_database("chatbot.db")
            except Exception:
                pass
        return res
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Failed to process document: {exc}"
        ) from exc


@app.get("/api/threads/{thread_id}/documents")
def list_thread_documents(thread_id: str) -> dict[str, Any]:
    """Retrieve all documents indexed for the specified thread."""
    return {
        "thread_id": thread_id,
        "documents": multi_doc_manager.get_documents(thread_id),
    }


# ---------------------------------------------------------------------------
# Persistent Files (Google Drive / Storage)
# ---------------------------------------------------------------------------
@app.get("/api/threads/{thread_id}/files")
def list_thread_files(thread_id: str, category: Optional[str] = None) -> dict[str, Any]:
    """List persistent files stored for a thread."""
    if not storage.enabled:
        return {"thread_id": thread_id, "files": []}
    files = storage.list_files(thread_id=thread_id, category=category)
    return {"thread_id": thread_id, "files": files}


@app.get("/api/files/{thread_id}/{category}/{filename:path}")
def download_file_by_category(thread_id: str, category: str, filename: str) -> Response:
    """Download a persistent file by category and filename."""
    if not storage.enabled:
        raise HTTPException(status_code=503, detail="Storage backend is not configured.")
    data = storage.download_bytes(thread_id=thread_id, category=category, filename=filename)
    if data is None:
        raise HTTPException(status_code=404, detail="File not found.")
    from storage.base import guess_mime_type
    mime_type = guess_mime_type(filename)
    safe_name = os.path.basename(filename)
    return Response(
        content=data,
        media_type=mime_type,
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@app.get("/api/files/{thread_id}/{filename:path}")
def download_workspace_file(thread_id: str, filename: str) -> Response:
    """Download a persistent workspace file by filename."""
    return download_file_by_category(thread_id=thread_id, category="workspace", filename=filename)


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> dict[str, Any]:
    """Handle standard Model Context Protocol (MCP) JSON-RPC 2.0 requests."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
    from src.mcp import mcp_server
    return mcp_server.handle_request(body)


# ---------------------------------------------------------------------------
# Auth, HITL & Observability Endpoints
# ---------------------------------------------------------------------------
class TokenRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/token")
def login_for_token(req: TokenRequest) -> dict[str, Any]:
    """Issue a JWT token for user credentials."""
    if req.username == "admin" and req.password in ("agent-pilot", "docupilot"):
        token = create_access_token(user_id="admin", role="admin")
    else:
        token = create_access_token(user_id=req.username, role="user")
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/hitl/pending")
def list_pending_approvals(thread_id: Optional[str] = None) -> list[dict[str, Any]]:
    """List pending human-in-the-loop tool approvals."""
    return hitl_manager.get_pending(thread_id=thread_id)


@app.post("/api/hitl/{request_id}/approve")
def approve_hitl_action(request_id: str) -> dict[str, Any]:
    """Approve a paused sensitive action."""
    success = hitl_manager.approve(request_id)
    if not success:
        raise HTTPException(status_code=404, detail="Request not found or not in pending state.")
    audit_logger.log("hitl_approval", f"Approved {request_id}", status="approved")
    return {"request_id": request_id, "status": "approved"}


@app.post("/api/hitl/{request_id}/reject")
def reject_hitl_action(request_id: str, reason: str = "User declined") -> dict[str, Any]:
    """Reject a paused sensitive action."""
    success = hitl_manager.reject(request_id, reason=reason)
    if not success:
        raise HTTPException(status_code=404, detail="Request not found or not in pending state.")
    audit_logger.log("hitl_rejection", f"Rejected {request_id}: {reason}", status="rejected")
    return {"request_id": request_id, "status": "rejected", "reason": reason}


@app.get("/api/observability/audit")
def get_audit_records(thread_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    """Query recent audit events for compliance."""
    return audit_logger.query(thread_id=thread_id, limit=limit)


@app.get("/api/observability/usage")
def get_usage_metrics(thread_id: Optional[str] = None) -> dict[str, Any]:
    """Get token consumption and cost metrics."""
    return cost_tracker.get_summary(thread_id=thread_id)


# ---------------------------------------------------------------------------
# Phase 6: Graph, Automation, Voice & Critic Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/graph/{entity}")
def query_graph_endpoint(entity: str) -> dict[str, Any]:
    """Retrieve connected knowledge graph nodes and relations for an entity."""
    from src.graph import knowledge_graph
    return knowledge_graph.query_subgraph(entity=entity)


class ScheduleTaskRequest(BaseModel):
    name: str
    interval_seconds: int = 3600
    payload: Optional[dict[str, Any]] = None


@app.post("/api/automation/schedule")
def schedule_task_endpoint(req: ScheduleTaskRequest) -> dict[str, Any]:
    """Schedule a recurring background task."""
    from src.automation import task_scheduler
    task = task_scheduler.schedule(req.name, req.interval_seconds, req.payload)
    return task.to_dict()


@app.get("/api/automation/tasks")
def list_tasks_endpoint() -> list[dict[str, Any]]:
    """List scheduled background tasks."""
    from src.automation import task_scheduler
    return task_scheduler.list_tasks()


class WorkflowRunRequest(BaseModel):
    name: str
    steps: list[dict[str, Any]]
    context: Optional[dict[str, Any]] = None


@app.post("/api/automation/workflow")
def run_workflow_endpoint(req: WorkflowRunRequest) -> dict[str, Any]:
    """Execute an autonomous multi-step workflow."""
    from src.automation import workflow_runner
    return workflow_runner.run_workflow(req.name, req.steps, req.context)


@app.post("/api/voice/transcribe")
async def voice_transcribe_endpoint(file: UploadFile = File(...)) -> dict[str, Any]:
    """Transcribe user audio stream into text."""
    from src.voice import audio_processor
    data = await file.read()
    return audio_processor.transcribe(data, filename=file.filename or "audio.wav")


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "en-US-Neural"
    speed: float = 1.0


@app.post("/api/voice/synthesize")
def voice_synthesize_endpoint(req: SynthesizeRequest) -> dict[str, Any]:
    """Synthesize text into streamable audio."""
    from src.voice import audio_processor
    return audio_processor.synthesize(req.text, voice=req.voice, speed=req.speed)


class CritiqueRequest(BaseModel):
    question: str
    context: str
    response: str


@app.post("/api/agent/critique")
def critique_response_endpoint(req: CritiqueRequest) -> dict[str, Any]:
    """Critique an assistant answer against reference context."""
    from src.agent import critic_agent
    return critic_agent.evaluate(req.question, req.context, req.response)




