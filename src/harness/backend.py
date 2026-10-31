"""DeepSeek Harness ChatBackend implementation for Agent-Pilot."""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Generator, Optional

from src.harness.config import HarnessSettings, get_harness_settings
from src.harness.errors import HarnessError, RuntimeUnavailable, SessionBusy
from src.harness.runtime import get_runtime_supervisor
from src.harness.sessions import get_session_mapper
from src.harness.store import upsert_harness_session
from src.harness.translate import EventTranslator, sanitize_error_message
from src.harness.wire import HarnessWireClient
from src.observability import audit_logger, cost_tracker, estimate_token_count

logger = logging.getLogger("harness.backend")


class HarnessBackend:
    """Chat backend driven by isolated tenant DeepSeek Harness runtimes."""

    def __init__(self, settings: Optional[HarnessSettings] = None):
        self.settings = settings or get_harness_settings()
        self.supervisor = get_runtime_supervisor()
        self.mapper = get_session_mapper()

    def stream_chat(
        self,
        message: str,
        thread_id: str,
        user_id: str,
        doc_id: Optional[str] = None,
        response_format: Optional[str] = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Stream conversational turn tokens and tool badges as SSE event dicts."""
        harness_session_id = self.mapper.get_harness_session_id(thread_id)
        upsert_harness_session(thread_id, user_id, harness_session_id)

        translator = EventTranslator()
        event_queue: queue.Queue[Optional[dict[str, Any]]] = queue.Queue()

        with self.mapper.acquire_session_lock(user_id, thread_id):
            runtime = self.supervisor.get_runtime(user_id)
            wire = HarnessWireClient(runtime)

            def on_notification(notification: dict[str, Any]) -> None:
                for sse_evt in translator.translate_event(notification):
                    event_queue.put(sse_evt)

            worker_err: list[Exception] = []

            def worker() -> None:
                try:
                    wire.run_turn(
                        session_id=harness_session_id,
                        prompt=message,
                        notification_callback=on_notification,
                        timeout=self.settings.turn_timeout_s,
                    )
                except Exception as exc:
                    worker_err.append(exc)
                finally:
                    event_queue.put(None)

            t = threading.Thread(target=worker, daemon=True)
            t.start()

            prompt_toks = estimate_token_count(message)

            try:
                while True:
                    evt = event_queue.get()
                    if evt is None:
                        break
                    yield evt

                if worker_err:
                    clean_msg = sanitize_error_message(str(worker_err[0]))
                    yield {"type": "error", "message": clean_msg}

                # Ensure done event is emitted exactly once
                if not translator.has_emitted_done:
                    translator.has_emitted_done = True
                    yield {"type": "done", "tools_used": translator.tools_used}

                # Record usage telemetry
                final_text = "".join(translator.collected_tokens)
                cost_tracker.record_usage(
                    thread_id, prompt_toks, estimate_token_count(final_text)
                )
                audit_logger.log(
                    "harness_turn_end",
                    "POST /api/chat/stream",
                    thread_id,
                    status="success",
                    details={"backend": "harness", "tools": translator.tools_used},
                )
            except Exception as exc:
                clean_err = sanitize_error_message(str(exc))
                yield {"type": "error", "message": clean_err}

    def invoke_chat(
        self,
        message: str,
        thread_id: str,
        user_id: str,
        doc_id: Optional[str] = None,
        response_format: Optional[str] = None,
    ) -> tuple[str, list[str]]:
        """Synchronously execute a chat turn and return (message_text, tools_used)."""
        tokens: list[str] = []
        tools: list[str] = []
        for evt in self.stream_chat(message, thread_id, user_id, doc_id, response_format):
            evt_type = evt.get("type")
            if evt_type == "token":
                tokens.append(evt.get("content", ""))
            elif evt_type == "tool":
                name = evt.get("name")
                if name and name not in tools:
                    tools.append(name)
            elif evt_type == "error":
                raise HarnessError(evt.get("message", "Error in harness turn"))
        return "".join(tokens), tools


_backend_instance: Optional[HarnessBackend] = None


def get_harness_backend() -> HarnessBackend:
    global _backend_instance
    if _backend_instance is None:
        _backend_instance = HarnessBackend()
    return _backend_instance

