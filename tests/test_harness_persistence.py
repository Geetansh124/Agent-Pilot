"""Unit tests for Harness persistence, message projection, and manifest verification."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from src.auth.database import get_db_connection, init_auth_db
from src.harness.config import HarnessSettings
from src.harness.store import (
    append_harness_event,
    clean_thread_persistence,
    get_harness_events,
    get_harness_session,
    upsert_harness_session,
)
from src.harness.sync import SessionSyncManager, compute_sha256


class TestHarnessPersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="harness_persist_")
        self.db_path = os.path.join(self.temp_dir, "persist_test.db")
        init_auth_db(self.db_path)

        self.settings = HarnessSettings(
            backend="harness",
            home_root=os.path.join(self.temp_dir, "homes"),
            path_salt="salt-persist-123",
        )
        self.sync_mgr = SessionSyncManager()
        self.sync_mgr.settings = self.settings

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_idempotent_event_append_and_messages_projection(self):
        thread_id = "th-persist-01"
        user_id = "user-persist"

        upsert_harness_session(thread_id, user_id, f"ap-{thread_id}", db_path=self.db_path)

        # Append turn 1 assistant message
        append_harness_event(
            thread_id=thread_id,
            seq=1,
            event_type="assistant/message",
            payload={"content": "First response from agent", "tool_calls": []},
            db_path=self.db_path,
        )

        # Verify event appended
        events = get_harness_events(thread_id, db_path=self.db_path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["seq"], 1)

        # Verify atomic projection into messages table
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, role, content FROM messages WHERE thread_id = ?", (thread_id,))
            msgs = cursor.fetchall()
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0]["role"], "assistant")
            self.assertEqual(msgs[0]["content"], "First response from agent")

        # Duplicate append with same seq must not duplicate event or projected message
        append_harness_event(
            thread_id=thread_id,
            seq=1,
            event_type="assistant/message",
            payload={"content": "Duplicate ignored", "tool_calls": []},
            db_path=self.db_path,
        )
        events_after = get_harness_events(thread_id, db_path=self.db_path)
        self.assertEqual(len(events_after), 1)

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM messages WHERE thread_id = ?", (thread_id,))
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_manifest_generation_and_checksum_verification(self):
        user_id = "user-manifest"
        thread_id = "th-manifest-01"

        jsonl_path, manifest_path = self.sync_mgr.get_session_paths(user_id, thread_id)
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write('{"seq": 1, "type": "turn"}\n')

        manifest = self.sync_mgr.write_manifest(user_id, thread_id, last_seq=1)
        self.assertIn("sha256", manifest)
        self.assertEqual(manifest["last_seq"], 1)

        # Verification succeeds on intact file
        self.assertTrue(self.sync_mgr.verify_manifest(user_id, thread_id))

        # Tampering or tail corruption invalidates checksum
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write('{"seq": 2, "corrupted": true}\n')
        self.assertFalse(self.sync_mgr.verify_manifest(user_id, thread_id))

    def test_clean_thread_persistence_removes_rows_and_files(self):
        user_id = "user-clean"
        thread_id = "th-clean-01"

        upsert_harness_session(thread_id, user_id, f"ap-{thread_id}", db_path=self.db_path)
        append_harness_event(thread_id, 1, "tool/call", {"name": "rag"}, db_path=self.db_path)

        jsonl_path, _ = self.sync_mgr.get_session_paths(user_id, thread_id)
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write("content")

        self.assertTrue(os.path.exists(jsonl_path))

        clean_thread_persistence(thread_id, user_id, settings=self.settings, db_path=self.db_path)

        # Database rows removed
        self.assertIsNone(get_harness_session(thread_id, db_path=self.db_path))
        self.assertEqual(len(get_harness_events(thread_id, db_path=self.db_path)), 0)
        # Workspace files removed
        self.assertFalse(os.path.exists(jsonl_path))


if __name__ == "__main__":
    unittest.main()
