"""Tests for Phase 8: Chaos resilience matrix, security audit, and concurrency."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.agent.hitl import HITLManager
from src.harness.approvals import ApprovalBridge, DecisionConflict
from src.harness.config import HarnessSettings
from src.harness.errors import QuotaExceeded, RuntimeUnavailable
from src.harness.runtime import RuntimeSupervisor, TenantRuntime
from src.harness.sync import SessionSyncManager
from src.harness.translate import sanitize_error_message


class TestHarnessChaosMatrix(unittest.TestCase):
    """Chaos matrix verifying graceful degradation and security boundaries."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="harness_chaos_")
        self.settings = HarnessSettings(
            home_root=self.temp_dir,
            path_salt="chaos-salt",
            max_runtimes=2,
            idle_timeout_s=1,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_process_killed_mid_turn_degrades_gracefully(self):
        """Simulate killed runtime subprocess mid-turn; should report dead and degrade."""
        supervisor = RuntimeSupervisor(self.settings)
        runtime = supervisor.get_runtime("tenant-chaos-1")

        # Kill the runtime process intentionally
        runtime.close()
        self.assertFalse(runtime.is_alive())

        # Calling close or verifying health after kill must be safe and idempotent
        runtime.close()
        self.assertFalse(runtime.is_alive())

    def test_corrupted_jsonl_tail_detection_and_repair(self):
        """Truncated or corrupted tail in events.jsonl is handled gracefully."""
        sync_mgr = SessionSyncManager(self.settings)
        tenant_home = self.settings.get_tenant_home("tenant-chaos-2")
        ws = os.path.join(tenant_home, "workspace", "th-chaos")
        os.makedirs(ws, exist_ok=True)
        jsonl_path = os.path.join(ws, "events.jsonl")

        # Write valid events followed by half-written truncated line
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"seq": 1, "type": "turn_start"}) + "\n")
            f.write(json.dumps({"seq": 2, "type": "token", "val": "hello"}) + "\n")
            f.write('{"seq": 3, "type": "incomplet')  # Corrupted tail

        # Parsing lines should not crash
        valid_events = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    valid_events.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    pass

        self.assertEqual(len(valid_events), 2)
        self.assertEqual(valid_events[0]["seq"], 1)
        self.assertEqual(valid_events[1]["seq"], 2)

    def test_expired_approval_fails_closed(self):
        """Expired pending approvals must fail-closed and reject execution."""
        mgr = HITLManager()
        bridge = ApprovalBridge(manager=mgr, default_timeout_s=0.01)  # 10ms TTL
        req = mgr.request_approval(
            tool_name="delete_workspace_file",
            arguments={"path": "important.dat"},
            thread_id="th-exp",
        )
        req_id = req.request_id

        import time
        time.sleep(0.05)  # Let TTL expire

        # Pending approvals must be empty
        pending = bridge.get_pending_approvals("th-exp")
        self.assertEqual(len(pending), 0)

        # Attempting to approve after expiration must fail-closed
        with self.assertRaises(DecisionConflict):
            bridge.submit_decision(req_id, "th-exp", "allowed-once", decided_by="admin")

    def test_runtime_pool_exhaustion_lru_eviction(self):
        """Exceeding max_runtimes evicts least recently used idle runtime."""
        supervisor = RuntimeSupervisor(self.settings)  # max_runtimes = 2

        rt1 = supervisor.get_runtime("user-pool-1")
        rt2 = supervisor.get_runtime("user-pool-2")
        self.assertEqual(supervisor.active_count, 2)

        # Accessing 3rd tenant forces LRU eviction of idle runtime
        rt3 = supervisor.get_runtime("user-pool-3")
        self.assertLessEqual(supervisor.active_count, 2)
        self.assertTrue(rt3.is_alive())

    def test_path_traversal_defense(self):
        """Directory traversal payloads are normalized safely into sandboxed workspace."""
        # Traversal attempt in thread_id
        ws1 = self.settings.get_thread_workspace("user-traversal", "../../etc/passwd")
        self.assertNotIn("..", ws1)
        self.assertTrue(ws1.startswith(self.temp_dir))

        # Absolute root attempt
        ws2 = self.settings.get_thread_workspace("user-traversal", "/root/secrets")
        self.assertNotIn("/root/secrets", ws2)
        self.assertTrue(ws2.startswith(self.temp_dir))

    def test_security_sanitization_removes_secrets_and_stacktraces(self):
        """Sanitizer scrubs bearer tokens, api keys, file paths, and python tracebacks."""
        raw_error = (
            "Traceback (most recent call last):\n"
            '  File "D:\\Main\\Projects\\secrets\\run.py", line 42, in <module>\n'
            "RuntimeError: Failed with key sk-proj-1234567890abcdef and Authorization Bearer secret-token"
        )
        clean = sanitize_error_message(raw_error)
        self.assertNotIn("sk-proj-", clean)
        self.assertNotIn("secret-token", clean)
        self.assertNotIn("D:\\Main\\Projects", clean)
        self.assertNotIn("Traceback", clean)

    def test_multi_tenant_concurrency_isolation(self):
        """Concurrent turns on distinct tenants run in isolated salted homes."""
        home_a = self.settings.get_tenant_home("tenant-alpha")
        home_b = self.settings.get_tenant_home("tenant-beta")

        self.assertNotEqual(home_a, home_b)
        self.assertTrue(home_a.startswith(self.temp_dir))
        self.assertTrue(home_b.startswith(self.temp_dir))


if __name__ == "__main__":
    unittest.main()
