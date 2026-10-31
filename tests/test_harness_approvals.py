"""Unit and integration tests for Harness Approval Bridge and HITL endpoints."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_server import app
from src.agent.hitl import HITLManager
from src.auth.auth import create_access_token
from src.harness.approvals import ApprovalBridge, DecisionConflict


class TestHarnessApprovals(unittest.TestCase):
    def setUp(self):
        self.hitl = HITLManager(auto_approve=False)
        self.bridge = ApprovalBridge(manager=self.hitl, default_timeout_s=0.2)
        self.client = TestClient(app)

        self.user_token = create_access_token(user_id="user_owner", role="user")
        self.attacker_token = create_access_token(user_id="user_attacker", role="user")
        self.owner_headers = {"Authorization": f"Bearer {self.user_token}", "Content-Type": "application/json"}
        self.attacker_headers = {"Authorization": f"Bearer {self.attacker_token}", "Content-Type": "application/json"}

    def test_bridge_approve_reject_and_cancel(self):
        req1 = self.hitl.request_approval("write_workspace_file", {"filename": "a.txt"}, "t-01")
        rec1 = self.bridge.submit_decision(req1.request_id, "t-01", "allowed-once")
        self.assertEqual(rec1["decision"], "allowed-once")
        self.assertEqual(self.hitl.get_request(req1.request_id)["status"], "approved")

        req2 = self.hitl.request_approval("delete_workspace_file", {"filename": "b.txt"}, "t-01")
        rec2 = self.bridge.submit_decision(req2.request_id, "t-01", "rejected")
        self.assertEqual(rec2["decision"], "rejected")
        self.assertEqual(self.hitl.get_request(req2.request_id)["status"], "rejected")

        req3 = self.hitl.request_approval("call_api", {"url": "https://api.com"}, "t-01")
        rec3 = self.bridge.submit_decision(req3.request_id, "t-01", "cancelled")
        self.assertEqual(rec3["decision"], "cancelled")

    def test_bridge_duplicate_decision_raises_conflict(self):
        req = self.hitl.request_approval("write_workspace_file", {"filename": "c.txt"}, "t-01")
        self.bridge.submit_decision(req.request_id, "t-01", "allowed-once")

        with self.assertRaises(DecisionConflict):
            self.bridge.submit_decision(req.request_id, "t-01", "allowed-once")

    def test_bridge_expired_request_fails_closed(self):
        req = self.hitl.request_approval("delete_workspace_file", {"filename": "d.txt"}, "t-02")
        # Simulate backdated timestamp to trigger expiration
        self.hitl._requests[req.request_id].created_at = "2020-01-01T00:00:00+00:00"

        pending = self.bridge.get_pending_approvals("t-02")
        self.assertEqual(len(pending), 0)
        self.assertEqual(self.hitl.get_request(req.request_id)["status"], "rejected")

    def test_bridge_questions_workflow(self):
        q = self.bridge.register_question(
            question_id="q-01",
            thread_id="t-03",
            prompt="Choose format",
            options=["CSV", "JSON"],
        )
        self.assertEqual(q["status"], "pending")

        ans = self.bridge.answer_question(
            question_id="q-01",
            thread_id="t-03",
            answers=[{"id": "fmt", "selected": ["JSON"]}],
        )
        self.assertEqual(ans["status"], "answered")

        with self.assertRaises(DecisionConflict):
            self.bridge.answer_question("q-01", "t-03", answers=[])

    @patch("api_server._user_owns_thread")
    @patch("src.harness.approval_routes.get_approval_bridge")
    def test_api_approval_endpoints_one_shot_and_ownership(self, mock_get_bridge, mock_owns_thread):
        mock_owns_thread.side_effect = lambda tid, uid, role="user": uid == "user_owner"
        mock_bridge = ApprovalBridge(manager=self.hitl)
        mock_get_bridge.return_value = mock_bridge

        req = self.hitl.request_approval("write_workspace_file", {"filename": "api.txt"}, "t-api")

        # GET approvals
        get_res = self.client.get("/api/threads/t-api/approvals", headers=self.owner_headers)
        self.assertEqual(get_res.status_code, 200)

        # Wrong user access denied (404)
        bad_get = self.client.get("/api/threads/t-api/approvals", headers=self.attacker_headers)
        self.assertEqual(bad_get.status_code, 404)

        # POST approval decision allowed-once
        post_res = self.client.post(
            f"/api/threads/t-api/approvals/{req.request_id}",
            json={"decision": "allowed-once"},
            headers=self.owner_headers,
        )
        self.assertEqual(post_res.status_code, 200)

        # POST duplicate decision returns 409
        dup_res = self.client.post(
            f"/api/threads/t-api/approvals/{req.request_id}",
            json={"decision": "allowed-once"},
            headers=self.owner_headers,
        )
        self.assertEqual(dup_res.status_code, 409)


if __name__ == "__main__":
    unittest.main()

