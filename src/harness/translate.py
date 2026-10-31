"""Translation of DeepSeek Harness events and notifications to Agent-Pilot SSE format."""
from __future__ import annotations

import re
from typing import Any, Generator

from src.security import sanitize_output

_SECRET_PATTERN = re.compile(r"(nvapi-[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]+|Bearer\s+[A-Za-z0-9._-]+)", re.IGNORECASE)
_PATH_PATTERN = re.compile(r"([A-Za-z]:\\[^\s\"'>]+|/(?:home|Users|var|tmp|etc|app)/[^\s\"'>]+)")


def sanitize_error_message(raw_message: str) -> str:
    """Sanitize error messages: redact secrets, absolute paths, and internal stack frames."""
    msg = _SECRET_PATTERN.sub("[REDACTED_SECRET]", str(raw_message))
    msg = _PATH_PATTERN.sub("[REDACTED_PATH]", msg)
    if "Traceback (most recent call last):" in msg:
        msg = msg.split("Traceback (most recent call last):")[0].strip() or "Internal runtime error occurred."
    return msg


class EventTranslator:
    """Converts harness JSON-RPC events into standard Agent-Pilot SSE payloads."""

    def __init__(self):
        self.tools_used: list[str] = []
        self.collected_tokens: list[str] = []
        self.has_emitted_done = False

    def translate_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Translate a single harness notification into zero or more SSE event dicts."""
        method = event.get("method")
        params = event.get("params", {})

        results: list[dict[str, Any]] = []

        if method == "ap/stream":
            delta = params.get("delta")
            if delta is None:
                delta = params.get("content")
            if delta is not None:
                tok = sanitize_output(str(delta))
                self.collected_tokens.append(tok)
                results.append({"type": "token", "content": tok})

        elif method == "session.event":
            event_type = params.get("type")
            data = params.get("data", {})

            if event_type == "tool/call":
                tool_name = data.get("name", "unknown_tool")
                if tool_name not in self.tools_used:
                    self.tools_used.append(tool_name)
                results.append({"type": "tool", "name": tool_name})

            elif event_type == "tool/result":
                tool_name = data.get("name", "")
                results.append({"type": "tool_result", "name": tool_name, "result": data.get("result")})

            elif event_type == "assistant/message":
                # Fallback to chunk replay if no live tokens were streamed
                if not self.collected_tokens:
                    stream = data.get("stream")
                    if stream and isinstance(stream, list):
                        for chunk in stream:
                            tok = sanitize_output(str(chunk))
                            self.collected_tokens.append(tok)
                            results.append({"type": "token", "content": tok})
                    elif data.get("content"):
                        tok = sanitize_output(str(data["content"]))
                        self.collected_tokens.append(tok)
                        results.append({"type": "token", "content": tok})

            elif event_type == "tool/error":
                err = data.get("error", {})
                clean_err = sanitize_error_message(err.get("message", "Tool execution error"))
                results.append({"type": "tool_error", "message": clean_err})

        elif method == "session.status":
            status = params.get("status")
            if status == "idle" and not self.has_emitted_done:
                self.has_emitted_done = True
                results.append({"type": "done", "tools_used": self.tools_used})

        return results

    def format_sse(self, event_dict: dict[str, Any]) -> str:
        """Format an event dict as standard SSE data line."""
        import json
        return f"data: {json.dumps(event_dict)}\n\n"

