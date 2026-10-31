"""Dynamic chat backend routing between LangGraph and DeepSeek Harness with failover."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Generator, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langraph_rag_backend import chatbot

from src.harness.backend import get_harness_backend
from src.harness.config import get_harness_settings
from src.harness.shadow import get_shadow_comparator
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
        # Stream primary LangGraph turn while capturing events for shadow comparison
        lg_events: list[dict[str, Any]] = []
        t0 = time.time()
        for evt in _langgraph_stream(message, thread_id, response_format):
            lg_events.append(evt)
            yield evt
        lg_latency = time.time() - t0

        def run_shadow(collected_lg: list[dict[str, Any]], primary_latency: float) -> None:
            try:
                harness = get_harness_backend()
                th_start = time.time()
                harness_events = list(harness.stream_chat(message, thread_id, user_id, doc_id, response_format))
                harness_latency = time.time() - th_start

                metric = get_shadow_comparator().record_turn(
                    prompt_id=thread_id,
                    langgraph_events=collected_lg,
                    harness_events=harness_events,
                    lg_latency_s=primary_latency,
                    harness_latency_s=harness_latency,
                )
                audit_logger.log(
                    "harness_shadow_compared",
                    f"Shadow comparison: tools_match={metric.tools_match}",
                    thread_id,
                    status="success" if metric.tools_match else "warning",
                    details={
                        "tools_match": metric.tools_match,
                        "lg_latency": primary_latency,
                        "harness_latency": harness_latency,
                    },
                )
            except Exception as shadow_err:
                logger.debug("Shadow harness run exception: %s", shadow_err)

        threading.Thread(target=run_shadow, args=(lg_events, lg_latency), daemon=True).start()
        return

    # Default: LangGraph
    yield from _langgraph_stream(message, thread_id, response_format)

