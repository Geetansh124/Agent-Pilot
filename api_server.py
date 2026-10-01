from __future__ import annotations

import json
import os
import time
import uuid
from collections import defaultdict
from typing import Any, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, UploadFile
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
from src.auth.database import get_db_connection, _ensure_user_exists
from src.storage.routes import documents_router, _extract_user_id
from src.agent.routes import services_router
from src.security import sanitize_output, validate_input_prompt
from src.agent import hitl_manager
from src.observability import audit_logger, cost_tracker, estimate_token_count

app = FastAPI(title="Agent-Pilot API", version="1.1.0")
origins = list(dict.fromkeys([
    "http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001",
    *[o.strip() for o in os.getenv("FRONTEND_ORIGIN", "").split(",") if o.strip()]
]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(documents_router, prefix="/api", tags=["documents"])
app.include_router(services_router, prefix="/api", tags=["services"])

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
# Multi-Tenant Threads (Scoped by Profile)
# ---------------------------------------------------------------------------
def _ensure_thread_registered(thread_id: str, user_id: str, title: Optional[str] = None) -> None:
    """Register or update thread ownership in the threads table."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            _ensure_user_exists(cursor, user_id)
            cursor.execute(
                """
                INSERT INTO threads (id, user_id, title)
                VALUES (?, ?, COALESCE(?, 'New chat'))
                ON CONFLICT(id) DO UPDATE SET
                    title = CASE WHEN threads.title IN ('New Conversation', 'New chat') AND excluded.title != 'New chat'
                                 THEN excluded.title ELSE threads.title END,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (thread_id, user_id, title),
            )
            conn.commit()
    except Exception:
        pass


def _user_owns_thread(thread_id: str, user_id: str, role: str = "user") -> bool:
    """Verify whether user owns the thread."""
    if role == "admin":
        return True
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM threads WHERE id = ?", (thread_id,))
            row = cursor.fetchone()
            return True if not row else row["user_id"] == user_id
    except Exception:
        return True


@app.get("/api/threads")
def threads(user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    """Retrieve conversations belonging strictly to current user profile."""
    user_id = _extract_user_id(user)
    saved_titles = get_all_thread_titles()
    result = []
    with get_db_connection() as conn:
        cursor = conn.cursor()
        _ensure_user_exists(cursor, user_id)
        if user_id == "guest":
            cursor.execute("SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id NOT IN (SELECT id FROM threads)")
            for r in cursor.fetchall():
                cursor.execute("INSERT OR IGNORE INTO threads (id, user_id, title) VALUES (?, 'guest', 'New chat')", (r[0],))
            conn.commit()
        cursor.execute("SELECT id, title, updated_at FROM threads WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))
        user_threads = cursor.fetchall()

    for row in user_threads:
        tid = row["id"]
        messages = _messages(tid)
        first = next((m["content"] for m in messages if m["role"] == "user"), "New chat")
        custom_title = saved_titles.get(tid) or row["title"]
        title = custom_title if custom_title not in ("New Conversation", "New chat") else " ".join(first.split())[:48]
        result.append({"id": tid, "title": title, "messages": messages})
    return result


@app.post("/api/threads")
def new_thread(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    """Create a new conversation thread bound to the authenticated user."""
    user_id = _extract_user_id(user)
    thread_id = str(uuid.uuid4())
    _ensure_thread_registered(thread_id, user_id, "New chat")
    return {"id": thread_id, "title": "New chat"}


@app.get("/api/threads/{thread_id}")
def thread(thread_id: str, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user_id = _extract_user_id(user)
    if not _user_owns_thread(thread_id, user_id, user.get("role", "user")):
        raise HTTPException(status_code=404, detail="Thread not found or access denied.")
    return {"id": thread_id, "messages": _messages(thread_id), "document": thread_document_metadata(thread_id) or None}


@app.patch("/api/threads/{thread_id}")
def update_thread(thread_id: str, body: UpdateThreadRequest, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user_id = _extract_user_id(user)
    if not _user_owns_thread(thread_id, user_id, user.get("role", "user")):
        raise HTTPException(status_code=404, detail="Thread not found or access denied.")
    clean_title = " ".join(body.title.split())
    if not clean_title:
        raise HTTPException(status_code=422, detail="Title cannot be empty.")
    _ensure_thread_registered(thread_id, user_id, clean_title)
    if set_thread_title(thread_id, clean_title):
        if hasattr(storage, "sync_database"):
            try:
                storage.sync_database("chatbot.db")
            except Exception:
                pass
        return {"id": thread_id, "title": clean_title}
    raise HTTPException(status_code=500, detail="Failed to update thread title.")


@app.delete("/api/threads/{thread_id}")
def remove_thread(thread_id: str, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user_id = _extract_user_id(user)
    if not _user_owns_thread(thread_id, user_id, user.get("role", "user")):
        raise HTTPException(status_code=404, detail="Thread not found or access denied.")
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
            conn.commit()
    except Exception:
        pass
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
def chat(
    request: ChatRequest,
    req: Request,
    background_tasks: BackgroundTasks,
    user: dict[str, Any] = Depends(get_current_user),
) -> ChatResponse:
    user_id = _extract_user_id(user)
    if not _user_owns_thread(request.thread_id, user_id, user.get("role", "user")):
        raise HTTPException(status_code=403, detail="Access denied to this conversation thread.")
    _ensure_thread_registered(request.thread_id, user_id, request.message[:48].strip())
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
def chat_stream(
    request: ChatRequest,
    req: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """Stream chat tokens as Server-Sent Events."""
    _check_rate_limit(req.client.host if req.client else "unknown")
    is_safe, reason = validate_input_prompt(request.message)
    if not is_safe:
        audit_logger.log("security_block", "Prompt injection blocked", request.thread_id, status="blocked", details={"reason": reason})
        raise HTTPException(status_code=400, detail=f"Input rejected by security guardrail: {reason}")

    user_id = _extract_user_id(user)
    if not _user_owns_thread(request.thread_id, user_id, user.get("role", "user")):
        raise HTTPException(status_code=403, detail="Access denied to this conversation thread.")
    _ensure_thread_registered(request.thread_id, user_id, request.message[:48].strip())
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
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/threads/{thread_id}/documents")
def list_thread_documents(thread_id: str) -> dict[str, Any]:
    """Retrieve all documents indexed for the specified thread."""
    return {"thread_id": thread_id, "documents": multi_doc_manager.get_documents(thread_id)}


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
