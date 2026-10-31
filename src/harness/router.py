"""Dynamic chat backend routing between LangGraph and DeepSeek Harness with failover."""
from __future__ import annotations

import logging
import threading
from typing import Any, Generator, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langraph_rag_backend import chatbot

from src.harness.backend import get_harness_backend
from src.harness.config import get_harness_settings
from src.observability import audit_logger
from src.security import sanitize_output

logger = logging.getLogger("harness.router")


def _langgraph_stream(
    message: str,
    thread_id: str,
    response_format: Optional[str] = None,
) -> Generator[dict[str, Any], None, None]:
    """Execute streaming chat using standard LangGraph backend."""
    config = {
        "configurable": {
            "thread_id": thread_id,
            "response_format": response_format or "text",
        },
        "metadata": {"thread_id": thread_id},
        "run_name": "chat_turn",
    }
    tools_used: list[str] = []
    try:
        for chunk, _ in chatbot.stream(
            {"messages": [HumanMessage(content=message)]},
            config=config,
            stream_mode="messages",
        ):
            if isinstance(chunk, ToolMessage):
                name = getattr(chunk, "name", None)
                if name and name not in tools_used:
                    tools_used.append(name)
                    yield {"type": "tool", "name": name}
            elif isinstance(chunk, AIMessage) and chunk.content:
                tok = sanitize_output(str(chunk.content))
                yield {"type": "token", "content": tok}
        yield {"type": "done", "tools_used": tools_used}
    except Exception as exc:
        yield {"type": "error", "message": str(exc)}


def route_chat_stream(
    message: str,
    thread_id: str,
    user_id: str,
    doc_id: Optional[str] = None,
    response_format: Optional[str] = None,
) -> Generator[dict[str, Any], None, None]:
    """Route chat streaming turn to active backend with graceful fallback."""
    settings = get_harness_settings()
    backend = settings.backend

    if backend == "harness":
        try:
            harness = get_harness_backend()
            yield from harness.stream_chat(
                message=message,
                thread_id=thread_id,
                user_id=user_id,
                doc_id=doc_id,
                response_format=response_format,
            )
            return
        except Exception as exc:
            logger.warning(
                "Harness backend failed for thread %s; falling back to LangGraph: %s",
                thread_id,
                exc,
            )
            audit_logger.log(
                "harness_fallback",
                "Fallback to LangGraph after Harness failure",
                thread_id,
                status="warning",
                details={"error": str(exc)},
            )
            # Fall through to LangGraph

    elif backend == "shadow":
        # Launch harness execution in background for telemetry shadow comparison
        def run_shadow() -> None:
            try:
                harness = get_harness_backend()
                list(harness.stream_chat(message, thread_id, user_id, doc_id, response_format))
            except Exception as shadow_err:
                logger.debug("Shadow harness run exception: %s", shadow_err)

        threading.Thread(target=run_shadow, daemon=True).start()

    # Default: LangGraph
    yield from _langgraph_stream(message, thread_id, response_format)

