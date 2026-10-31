"""Unit and integration tests for DeepSeek Harness chat backend and SSE streaming."""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api_server import app
from src.auth.auth import create_access_token
from src.harness.backend import HarnessBackend
from src.harness.config import HarnessSettings, get_harness_settings, reset_harness_settings
from src.harness.errors import RuntimeUnavailable
from src.harness.router import route_chat_stream
from src.harness.translate import EventTranslator, sanitize_error_message


class TestHarnessChatAndSSE(unittest.TestCase):
    def setUp(self):
        reset_harness_settings()
        self.client = TestClient(app)
        self.token = create_access_token(user_id="test_user_01", role="user")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def tearDown(self):
        reset_harness_settings()

    def test_sanitize_error_message_redacts_secrets_and_paths(self):
        leaked_secret = "Failed calling provider with key nvapi-abc123XYZ_key"
        sanitized = sanitize_error_message(leaked_secret)
        self.assertNotIn("nvapi-", sanitized)
        self.assertIn("[REDACTED_SECRET]", sanitized)

        leaked_path = r"Error opening file D:\Main\Projects\Secret\file.py"
        sanitized_path = sanitize_error_message(leaked_path)
        self.assertNotIn(r"D:\Main\Projects", sanitized_path)
        self.assertIn("[REDACTED_PATH]", sanitized_path)

    def test_event_translator_text_and_tool_events(self):
        translator = EventTranslator()

        tool_evt = {
            "method": "session.event",
            "params": {
                "type": "tool/call",
                "data": {"name": "rag_tool", "arguments": {"query": "test"}},
            },
        }
        res1 = translator.translate_event(tool_evt)
        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["type"], "tool")
        self.assertEqual(res1[0]["name"], "rag_tool")

        msg_evt = {
            "method": "session.event",
            "params": {
                "type": "assistant/message",
                "data": {"stream": ["Hello", " world!"], "content": "Hello world!"},
            },
        }
        res2 = translator.translate_event(msg_evt)
        self.assertEqual(len(res2), 2)
        self.assertEqual(res2[0]["content"], "Hello")
        self.assertEqual(res2[1]["content"], " world!")

        idle_evt = {
            "method": "session.status",
            "params": {"status": "idle"},
        }
        res3 = translator.translate_event(idle_evt)
        self.assertEqual(len(res3), 1)
        self.assertEqual(res3[0]["type"], "done")
        self.assertEqual(res3[0]["tools_used"], ["rag_tool"])

    def test_harness_backend_streaming_and_invoke(self):
        backend = HarnessBackend()
        events = list(backend.stream_chat(
            message="What is the architecture?",
            thread_id="test-thread-01",
            user_id="test_user_01",
        ))
        types = [e.get("type") for e in events]
        self.assertIn("token", types)
        self.assertIn("done", types)

        text, tools = backend.invoke_chat(
            message="Hello",
            thread_id="test-thread-02",
            user_id="test_user_01",
        )
        self.assertTrue(len(text) > 0)

    @patch("src.harness.router.get_harness_settings")
    def test_router_fallback_to_langgraph_on_harness_error(self, mock_settings):
        mock_settings.return_value = HarnessSettings(backend="harness")
        with patch("src.harness.router.get_harness_backend") as mock_backend:
            mock_inst = MagicMock()
            mock_inst.stream_chat.side_effect = RuntimeUnavailable("Process crashed")
            mock_backend.return_value = mock_inst

            # Must not crash; must fall back to LangGraph stream
            with patch("src.harness.router._langgraph_stream") as mock_langgraph:
                mock_langgraph.return_value = iter([{"type": "token", "content": "LangGraph fallback"}])
                evts = list(route_chat_stream("hi", "th-fallback", "user-01"))
                self.assertEqual(len(evts), 1)
                self.assertEqual(evts[0]["content"], "LangGraph fallback")

    def test_api_chat_stream_endpoint_with_harness_backend(self):
        with patch.dict(os.environ, {"AGENT_BACKEND": "harness"}):
            reset_harness_settings()
            payload = {
                "message": "Hello Agent-Pilot",
                "thread_id": "api-stream-thread-10",
            }
            resp = self.client.post("/api/chat/stream", json=payload, headers=self.headers)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/event-stream", resp.headers["content-type"])
            body_text = resp.text
            self.assertIn("data: ", body_text)
            self.assertIn('"type": "token"', body_text)
            self.assertIn('"type": "done"', body_text)


if __name__ == "__main__":
    unittest.main()

