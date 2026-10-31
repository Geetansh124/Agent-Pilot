"""Tests for Phase 7: Observability, per-tenant metrics, cost tracking, and quota enforcement."""
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_server import app
from src.auth import create_access_token
from src.harness.config import HarnessSettings, reset_harness_settings
from src.harness.errors import QuotaExceeded
from src.harness.metrics import (
    HarnessMetricsTracker,
    calculate_harness_cost,
    get_metrics_tracker,
)
from src.observability import audit_logger


class TestHarnessMetricsAndQuotas(unittest.TestCase):
    """Metrics accounting, cost calculation, and quota enforcement test suite."""

    def setUp(self):
        reset_harness_settings()
        self.tracker = get_metrics_tracker()
        self.tracker.reset()
        self.client = TestClient(app)

    def tearDown(self):
        reset_harness_settings()

    def test_cost_calculation(self):
        """Cost is accurately calculated per million tokens."""
        # default: input $0.14/M, output $0.28/M
        cost = calculate_harness_cost(prompt_tokens=1_000_000, completion_tokens=1_000_000)
        self.assertAlmostEqual(cost, 0.42, places=4)

        cost_partial = calculate_harness_cost(prompt_tokens=500, completion_tokens=1500)
        self.assertGreater(cost_partial, 0.0)

    def test_two_tenants_metrics_and_cost_snapshot(self):
        """Metrics snapshot displays distinct counts, token totals, and costs for two tenants."""
        # Tenant A: 2 turns
        self.tracker.start_turn("tenant-A", "th-A1")
        self.tracker.end_turn("tenant-A", "th-A1", prompt_tokens=1000, completion_tokens=2000)

        self.tracker.start_turn("tenant-A", "th-A2")
        self.tracker.record_tool_call("tenant-A", "th-A2", "rag_tool")
        self.tracker.end_turn("tenant-A", "th-A2", prompt_tokens=500, completion_tokens=1500)

        # Tenant B: 1 turn
        self.tracker.start_turn("tenant-B", "th-B1")
        self.tracker.end_turn("tenant-B", "th-B1", prompt_tokens=2000, completion_tokens=4000)

        summary = self.tracker.get_summary()

        self.assertEqual(summary["tenant_count"], 2)
        self.assertEqual(summary["total_turns"], 3)
        self.assertEqual(summary["total_tokens"], (1000 + 2000) + (500 + 1500) + (2000 + 4000))
        self.assertEqual(summary["total_tool_calls"], 1)

        tenants = summary["tenants"]
        self.assertIn("tenant-A", tenants)
        self.assertIn("tenant-B", tenants)

        self.assertEqual(tenants["tenant-A"]["total_turns"], 2)
        self.assertEqual(tenants["tenant-A"]["total_tokens"], 5000)
        self.assertGreater(tenants["tenant-A"]["total_cost_usd"], 0.0)

        self.assertEqual(tenants["tenant-B"]["total_turns"], 1)
        self.assertEqual(tenants["tenant-B"]["total_tokens"], 6000)
        self.assertGreater(tenants["tenant-B"]["total_cost_usd"], 0.0)

    def test_concurrency_quota_exceeded_raises_and_audits(self):
        """Exceeding max concurrent turns raises QuotaExceeded and logs audit entry."""
        settings = HarnessSettings(max_concurrent_turns=2)

        self.tracker.start_turn("tenant-C", "th-C1", settings=settings)
        self.tracker.start_turn("tenant-C", "th-C2", settings=settings)

        audit_events = []
        with patch.object(audit_logger, "log", side_effect=lambda *args, **kwargs: audit_events.append((args, kwargs))):
            with self.assertRaises(QuotaExceeded):
                self.tracker.start_turn("tenant-C", "th-C3", settings=settings)

        # Verify audit log was emitted
        quota_audits = [e for e in audit_events if e[0][0] == "harness_quota_exceeded"]
        self.assertGreaterEqual(len(quota_audits), 1)

    def test_max_tool_calls_quota_exceeded(self):
        """Exceeding max tool calls on a thread raises QuotaExceeded."""
        settings = HarnessSettings(max_tool_calls=2)
        self.tracker.start_turn("tenant-D", "th-D1", settings=settings)

        self.tracker.record_tool_call("tenant-D", "th-D1", "tool_1", settings=settings)
        self.tracker.record_tool_call("tenant-D", "th-D1", "tool_2", settings=settings)

        with self.assertRaises(QuotaExceeded):
            self.tracker.record_tool_call("tenant-D", "th-D1", "tool_3", settings=settings)

    def test_admin_metrics_endpoint_access_control(self):
        """GET /api/admin/metrics/harness requires admin role."""
        user_token = create_access_token(user_id="standard_user", role="user")
        admin_token = create_access_token(user_id="admin_user", role="admin")

        # Regular user -> 403 Forbidden
        res_user = self.client.get(
            "/api/admin/metrics/harness",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        self.assertEqual(res_user.status_code, 403)

        # Admin user -> 200 OK
        res_admin = self.client.get(
            "/api/admin/metrics/harness",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(res_admin.status_code, 200)
        data = res_admin.json()
        self.assertIn("total_turns", data)
        self.assertIn("tenants", data)

    def test_chat_stream_quota_returns_429(self):
        """When quota is exceeded during turn, endpoint returns 429 with Retry-After header."""
        user_token = create_access_token(user_id="quota_test_user", role="user")

        with patch.dict(os.environ, {"AGENT_BACKEND": "harness"}):
            reset_harness_settings()
            with patch(
                "src.harness.backend.HarnessBackend.stream_chat",
                return_value=[{"type": "error", "status": 429, "message": "Maximum concurrent turns exceeded.", "retry_after": 5}],
            ):
                res = self.client.post(
                    "/api/chat",
                    headers={"Authorization": f"Bearer {user_token}"},
                    json={"thread_id": "th-q-test", "message": "hello quota"},
                )
                self.assertEqual(res.status_code, 429)
                self.assertEqual(res.headers.get("Retry-After"), "5")


if __name__ == "__main__":
    unittest.main()

