"""Unit tests for DeepSeek Harness runtime supervisor, tenancy isolation, and concurrency."""
import os
import shutil
import tempfile
import time
import unittest

from src.auth.database import init_auth_db
from src.harness.config import HarnessSettings
from src.harness.errors import RuntimeUnavailable, SessionBusy
from src.harness.runtime import RuntimeSupervisor, TenantRuntime
from src.harness.sessions import SessionMapper
from src.harness.store import get_harness_session, upsert_harness_session, verify_session_ownership


class TestHarnessSupervisorAndTenancy(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="harness_test_")
        self.db_path = os.path.join(self.temp_dir, "test_harness.db")
        init_auth_db(self.db_path)

        self.settings = HarnessSettings(
            backend="harness",
            home_root=os.path.join(self.temp_dir, "homes"),
            path_salt="test-super-secret-salt-123",
            max_runtimes=2,  # Small pool to test LRU
            idle_timeout_s=1,  # Short timeout to test idle eviction
        )
        self.supervisor = RuntimeSupervisor(self.settings)
        self.mapper = SessionMapper(self.settings)

    def tearDown(self):
        self.supervisor.close_all()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_two_tenants_have_distinct_salted_homes(self):
        tenant_a = "user_alpha"
        tenant_b = "user_beta"

        home_a = self.settings.get_tenant_home(tenant_a)
        home_b = self.settings.get_tenant_home(tenant_b)

        self.assertNotEqual(home_a, home_b)
        self.assertTrue(os.path.isabs(home_a))
        self.assertTrue(os.path.isabs(home_b))
        self.assertIn(self.settings.get_tenant_hash(tenant_a), home_a)
        self.assertIn(self.settings.get_tenant_hash(tenant_b), home_b)

    def test_runtime_lazy_launch_and_process_reaping(self):
        user_id = "tenant_test_launch"
        runtime = self.supervisor.get_runtime(user_id)
        self.assertTrue(runtime.is_alive())
        self.assertTrue(runtime.is_initialized)

        # Close and verify process reaped
        runtime.close()
        self.assertFalse(runtime.is_alive())
        self.assertIsNone(runtime.process)

    def test_lru_pool_eviction(self):
        # Pool size is 2
        rt1 = self.supervisor.get_runtime("user_1")
        pid1 = rt1.process.pid if rt1.process else None
        time.sleep(0.05)

        rt2 = self.supervisor.get_runtime("user_2")
        self.assertEqual(len(self.supervisor._runtimes), 2)

        # Request user_3: should evict user_1 (the LRU)
        rt3 = self.supervisor.get_runtime("user_3")
        self.assertEqual(len(self.supervisor._runtimes), 2)
        self.assertNotIn("user_1", self.supervisor._runtimes)
        self.assertIn("user_2", self.supervisor._runtimes)
        self.assertIn("user_3", self.supervisor._runtimes)
        self.assertFalse(rt1.is_alive())

    def test_idle_eviction(self):
        rt = self.supervisor.get_runtime("user_idle")
        self.assertTrue(rt.is_alive())
        time.sleep(1.2)  # Exceed idle_timeout_s=1

        # Next call to supervisor triggers idle cleanup
        self.supervisor._evict_expired_unlocked()
        self.assertNotIn("user_idle", self.supervisor._runtimes)
        self.assertFalse(rt.is_alive())

    def test_per_session_concurrency_lock(self):
        user_id = "tenant_lock"
        thread_id = "thread_01"

        with self.mapper.acquire_session_lock(user_id, thread_id):
            # Attempting to acquire same session should raise SessionBusy
            with self.assertRaises(SessionBusy):
                with self.mapper.acquire_session_lock(user_id, thread_id, timeout=0.01):
                    pass

        # Different thread for same user can be acquired concurrently
        with self.mapper.acquire_session_lock(user_id, "thread_02"):
            pass

    def test_session_ownership_verification_denies_cross_tenant_resume(self):
        thread_id = "thread_owned"
        owner_id = "legit_user"
        attacker_id = "malicious_user"

        upsert_harness_session(
            thread_id=thread_id,
            user_id=owner_id,
            harness_session_id=self.mapper.get_harness_session_id(thread_id),
            db_path=self.db_path,
        )

        self.assertTrue(verify_session_ownership(thread_id, owner_id, db_path=self.db_path))
        self.assertFalse(verify_session_ownership(thread_id, attacker_id, db_path=self.db_path))


if __name__ == "__main__":
    unittest.main()

