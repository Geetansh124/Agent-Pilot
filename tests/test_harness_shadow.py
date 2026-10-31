"""Tests for Phase 6: Live streaming forwarder and shadow evaluation."""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from src.harness.shadow import ShadowComparator, get_shadow_comparator
from src.harness.translate import EventTranslator
from src.harness.wire import HarnessWireClient, is_stream_forwarder_available


class TestHarnessStreaming(unittest.TestCase):
    """Token order, live forwarder deltas, and fallback tests."""

    def test_live_stream_forwarder_token_order(self):
        """Tokens emitted via ap/stream should maintain exact order without duplicates."""
        translator = EventTranslator()

        events = [
            {"method": "session.status", "params": {"sessionId": "s-1", "status": "busy"}},
            {"method": "ap/stream", "params": {"sessionId": "s-1", "delta": "First "}},
            {"method": "ap/stream", "params": {"sessionId": "s-1", "delta": "second "}},
            {"method": "ap/stream", "params": {"sessionId": "s-1", "delta": "third."}},
            # When assistant/message arrives at end, it shouldn't re-emit duplicates
            {
                "method": "session.event",
                "params": {
                    "sessionId": "s-1",
                    "type": "assistant/message",
                    "data": {"content": "First second third."},
                },
            },
            {"method": "session.status", "params": {"sessionId": "s-1", "status": "idle"}},
        ]

        sse_events = []
        for e in events:
            sse_events.extend(translator.translate_event(e))

        tokens = [ev["content"] for ev in sse_events if ev.get("type") == "token"]
        self.assertEqual(tokens, ["First ", "second ", "third."])
        self.assertEqual(translator.collected_tokens, ["First ", "second ", "third."])

        # Verify done event
        done_events = [ev for ev in sse_events if ev.get("type") == "done"]
        self.assertEqual(len(done_events), 1)

    def test_fallback_replay_when_stream_forwarder_absent(self):
        """When no ap/stream events arrive, assistant/message stream list is replayed in order."""
        translator = EventTranslator()

        events = [
            {"method": "session.status", "params": {"sessionId": "s-2", "status": "busy"}},
            {
                "method": "session.event",
                "params": {
                    "sessionId": "s-2",
                    "type": "assistant/message",
                    "data": {"stream": ["Alpha", " ", "Beta", " ", "Gamma"]},
                },
            },
            {"method": "session.status", "params": {"sessionId": "s-2", "status": "idle"}},
        ]

        sse_events = []
        for e in events:
            sse_events.extend(translator.translate_event(e))

        tokens = [ev["content"] for ev in sse_events if ev.get("type") == "token"]
        self.assertEqual(tokens, ["Alpha", " ", "Beta", " ", "Gamma"])

    def test_interleaved_tool_and_streaming_turn_order(self):
        """Tool call and result must precede tokens and done event in correct order."""
        translator = EventTranslator()

        events = [
            {"method": "session.status", "params": {"sessionId": "s-3", "status": "busy"}},
            {
                "method": "session.event",
                "params": {
                    "sessionId": "s-3",
                    "type": "tool/call",
                    "data": {"name": "rag_tool", "arguments": {"query": "test"}},
                },
            },
            {
                "method": "session.event",
                "params": {
                    "sessionId": "s-3",
                    "type": "tool/result",
                    "data": {"name": "rag_tool", "result": {"docs": 2}},
                },
            },
            {"method": "ap/stream", "params": {"sessionId": "s-3", "delta": "Based on "}},
            {"method": "ap/stream", "params": {"sessionId": "s-3", "delta": "the search..."}},
            {"method": "session.status", "params": {"sessionId": "s-3", "status": "idle"}},
        ]

        sse_events = []
        for e in events:
            sse_events.extend(translator.translate_event(e))

        event_types = [ev.get("type") for ev in sse_events]
        self.assertEqual(event_types, ["tool", "tool_result", "token", "token", "done"])
        self.assertEqual(sse_events[0]["name"], "rag_tool")
        self.assertEqual(sse_events[-1]["tools_used"], ["rag_tool"])

    def test_stream_forwarder_plugin_detection(self):
        """is_stream_forwarder_available should correctly inspect dist presence."""
        self.assertTrue(is_stream_forwarder_available())


class TestShadowEvaluation(unittest.TestCase):
    """Shadow comparison metrics, 40-turn benchmark, and promotion criteria."""

    def setUp(self):
        self.comparator = ShadowComparator()

    def test_single_turn_shadow_comparison(self):
        """Comparison captures tool match, token difference, and latencies without raw text."""
        lg_events = [
            {"type": "tool", "name": "rag_tool"},
            {"type": "token", "content": "LangGraph response here"},
            {"type": "done", "tools_used": ["rag_tool"]},
        ]
        harness_events = [
            {"type": "tool", "name": "rag_tool"},
            {"type": "token", "content": "Harness response here"},
            {"type": "done", "tools_used": ["rag_tool"]},
        ]

        metric = self.comparator.record_turn(
            prompt_id="test-p1",
            langgraph_events=lg_events,
            harness_events=harness_events,
            lg_latency_s=0.150,
            harness_latency_s=0.160,
        )

        self.assertTrue(metric.tools_match)
        self.assertEqual(metric.tools_langgraph, ["rag_tool"])
        self.assertEqual(metric.tools_harness, ["rag_tool"])
        self.assertFalse(metric.safety_violation)

    def test_safety_violation_detection(self):
        """Comparator flags secret leakage in harness output."""
        lg_events = [{"type": "token", "content": "safe output"}]
        leaky_harness_events = [{"type": "token", "content": "leak nvapi-1234567890abcdef"}]

        metric = self.comparator.record_turn(
            prompt_id="test-p2",
            langgraph_events=lg_events,
            harness_events=leaky_harness_events,
            lg_latency_s=0.10,
            harness_latency_s=0.11,
        )

        self.assertTrue(metric.safety_violation)
        summary = self.comparator.get_aggregate_summary()
        self.assertEqual(summary["safety_violations"], 1)
        self.assertFalse(summary["passed_promotion_criteria"])

    def test_forty_turn_shadow_benchmark_meets_promotion_gate(self):
        """40 shadow prompt turns evaluate parity >=95%, 0 safety violations, and p95 within +25%."""
        self.comparator.reset()

        for i in range(40):
            tools = ["rag_tool"] if (i % 2 == 0) else []
            # 39 out of 40 match (97.5% parity)
            harness_tools = tools if i != 17 else (["rag_tool"] if not tools else [])

            lg_evts = [{"type": "tool", "name": t} for t in tools] + [
                {"type": "token", "content": f"Answer from LangGraph for prompt {i}"}
            ]
            h_evts = [{"type": "tool", "name": t} for t in harness_tools] + [
                {"type": "token", "content": f"Answer from Harness for prompt {i}"}
            ]

            # Latencies: Harness p95 within 15% of LangGraph
            lg_lat = 0.200 + (i * 0.005)
            h_lat = 0.210 + (i * 0.005)

            self.comparator.record_turn(
                prompt_id=f"bench-{i}",
                langgraph_events=lg_evts,
                harness_events=h_evts,
                lg_latency_s=lg_lat,
                harness_latency_s=h_lat,
            )

        summary = self.comparator.get_aggregate_summary()

        self.assertEqual(summary["total_turns"], 40)
        self.assertGreaterEqual(summary["tool_parity_pct"], 95.0)
        self.assertEqual(summary["safety_violations"], 0)
        self.assertLessEqual(summary["latency_overhead_pct"], 25.0)
        self.assertTrue(summary["passed_promotion_criteria"])


if __name__ == "__main__":
    unittest.main()

