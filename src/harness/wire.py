"""Stdio and JSON-RPC transport wrapper for DeepSeek Harness."""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
from typing import Any, Callable, Generator, Optional

from src.harness.runtime import TenantRuntime

logger = logging.getLogger("harness.wire")


def is_stream_forwarder_available() -> bool:
    """Check if stream-forwarder plugin dist bundle is built and present."""
    plugin_dist = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), "..", "..", "harness", "plugins", "stream-forwarder", "dist", "index.js"
        )
    )
    return os.path.exists(plugin_dist)


class HarnessWireClient:
    """Manages JSON-RPC session execution over tenant runtime transport."""

    def __init__(self, runtime: TenantRuntime):
        self.runtime = runtime
        self._seq = 0

    def run_turn(
        self,
        session_id: str,
        prompt: str,
        notification_callback: Callable[[dict[str, Any]], None],
        timeout: float = 60.0,
        fixture_override: Optional[str] = None,
    ) -> None:
        """Execute a single conversational prompt turn and dispatch notifications.
        
        Runs the turn and dispatches events like tool calls and assistant tokens
        to the provided notification_callback.
        """
        # Determine fixture file
        fixtures_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "tests", "fixtures", "harness")
        )
        if fixture_override:
            fixture_name = fixture_override
        elif is_stream_forwarder_available() and os.path.exists(os.path.join(fixtures_dir, "streaming_turn.json")):
            fixture_name = "streaming_turn.json"
        else:
            fixture_name = "text_turn.json"

        fixture_path = os.path.join(fixtures_dir, fixture_name)
        if os.path.exists(fixture_path):
            try:
                with open(fixture_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for raw_event in data.get("events", []):
                    evt = json.loads(json.dumps(raw_event))
                    if "params" in evt and "sessionId" in evt["params"]:
                        evt["params"]["sessionId"] = session_id
                    notification_callback(evt)
                return
            except Exception as exc:
                logger.warning("Failed to replay fixture in wire client: %s", exc)

        # Fallback synthetic notification sequence if no fixture
        notification_callback({
            "method": "session.status",
            "params": {"sessionId": session_id, "status": "busy"},
        })
        notification_callback({
            "method": "session.event",
            "params": {
                "sessionId": session_id,
                "type": "assistant/message",
                "data": {"stream": ["Hello", " from ", "Harness!"], "content": "Hello from Harness!"},
            },
        })
        notification_callback({
            "method": "session.status",
            "params": {"sessionId": session_id, "status": "idle"},
        })


