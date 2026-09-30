"""Unit and integration tests for Phase 2: Google Drive & Multi-Tenant Storage Adapter."""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.auth import create_access_token
from src.auth.database import (
    create_user,
    delete_user_document_record,
    get_user_document,
    init_auth_db,
    list_user_documents,
    save_document_record,
)
from src.storage.routes import documents_router
from storage.local import LocalStorageBackend


class TestPhase2StorageAdapter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_chatbot.db")
        self.storage_dir = os.path.join(self.temp_dir.name, "storage")
        os.makedirs(self.storage_dir, exist_ok=True)

        self._orig_env_db = os.environ.get("CHATBOT_DB_PATH")
        os.environ["CHATBOT_DB_PATH"] = self.db_path
        init_auth_db(self.db_path)

        # Initialize local storage backend pointing to isolated test directory
        self.storage_backend = LocalStorageBackend(base_dir=self.storage_dir)

        # Patch global storage in storage module and route module
        import storage as storage_mod
        import src.storage.routes as routes_mod
        self._orig_storage = storage_mod.storage
        storage_mod.storage = self.storage_backend
        routes_mod.storage = self.storage_backend

        # Setup test app
        self.app = FastAPI()
        self.app.include_router(documents_router, prefix="/api")
        self.client = TestClient(self.app)

        # Create two test users for tenant isolation tests
        self.user_a = create_user("alice_tenant@example.com", "Password123!", "Alice Tenant", db_path=self.db_path)
        self.user_b = create_user("bob_tenant@example.com", "Password123!", "Bob Tenant", db_path=self.db_path)

        self.token_a = create_access_token(self.user_a["id"], role="user")
        self.token_b = create_access_token(self.user_b["id"], role="user")

    def tearDown(self):
        import gc
        import storage as storage_mod
        import src.storage.routes as routes_mod
        storage_mod.storage = self._orig_storage
        routes_mod.storage = self._orig_storage

        if self._orig_env_db is not None:
            os.environ["CHATBOT_DB_PATH"] = self._orig_env_db
        else:
            os.environ.pop("CHATBOT_DB_PATH", None)

        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_save_user_document_storage_adapter(self):
        """Tests that storage organizes files under users/{user_id}/documents/{doc_id}/."""
        sample_bytes = b"%PDF-1.4 sample PDF document content"
        res = self.storage_backend.save_user_document(
            user_id=self.user_a["id"],
            doc_id="doc-test-1",
            filename="quarterly_report.pdf",
            file_bytes=sample_bytes,
            mime_type="application/pdf",
        )

        self.assertEqual(res["doc_id"], "doc-test-1")
        self.assertEqual(res["user_id"], self.user_a["id"])
        self.assertEqual(res["size_bytes"], len(sample_bytes))
        self.assertTrue(res["success"])

        # Check physical folder hierarchy on disk
        expected_path = (
            Path(self.storage_dir) / "users" / self.user_a["id"] / "documents" / "doc-test-1" / "quarterly_report.pdf"
        )
        self.assertTrue(expected_path.exists())
        self.assertEqual(expected_path.read_bytes(), sample_bytes)

        # Check metadata.json alongside document
        meta_path = expected_path.parent / "metadata.json"
        self.assertTrue(meta_path.exists())

        # Test download
        downloaded = self.storage_backend.load_user_document_bytes(
            user_id=self.user_a["id"],
            doc_id="doc-test-1",
            filename="quarterly_report.pdf",
        )
        self.assertEqual(downloaded, sample_bytes)

    def test_database_document_crud_and_tenant_scoping(self):
        """Tests database persistence in documents table and multi-tenant isolation."""
        doc_a = save_document_record(
            doc_id="doc-a-1",
            user_id=self.user_a["id"],
            filename="alice_secret.pdf",
            size_bytes=1024,
            mime_type="application/pdf",
            drive_file_id="drive-12345",
            drive_web_link="https://drive.google.com/file/d/12345/view",
            chunks_count=5,
            db_path=self.db_path,
        )
        self.assertEqual(doc_a["id"], "doc-a-1")
        self.assertEqual(doc_a["drive_web_link"], "https://drive.google.com/file/d/12345/view")

        # User A can retrieve their document
        fetched_a = get_user_document("doc-a-1", self.user_a["id"], db_path=self.db_path)
        self.assertIsNotNone(fetched_a)
        self.assertEqual(fetched_a["filename"], "alice_secret.pdf")

        # User B CANNOT access User A's document (tenant isolation)
        fetched_b = get_user_document("doc-a-1", self.user_b["id"], db_path=self.db_path)
        self.assertIsNone(fetched_b)

        # List documents returns only User A's documents
        list_a = list_user_documents(self.user_a["id"], db_path=self.db_path)
        self.assertEqual(len(list_a), 1)
        self.assertEqual(list_a[0]["id"], "doc-a-1")

        list_b = list_user_documents(self.user_b["id"], db_path=self.db_path)
        self.assertEqual(len(list_b), 0)

        # Deleting User A's document by User B fails
        deleted_by_b = delete_user_document_record("doc-a-1", self.user_b["id"], db_path=self.db_path)
        self.assertFalse(deleted_by_b)

        # Deleting by owner succeeds
        deleted_by_a = delete_user_document_record("doc-a-1", self.user_a["id"], db_path=self.db_path)
        self.assertTrue(deleted_by_a)

    def test_api_document_upload_and_list_endpoints(self):
        """Tests HTTP endpoints for /api/documents/upload and /api/documents."""
        # 1. Upload document for User A
        file_content = b"Financial report FY2026: Revenue up 34%."
        files = {"file": ("financial_report.pdf", io.BytesIO(file_content), "application/pdf")}
        headers_a = {"Authorization": f"Bearer {self.token_a}"}

        upload_res = self.client.post("/api/documents/upload", files=files, headers=headers_a)
        self.assertEqual(upload_res.status_code, 201)
        upload_data = upload_res.json()
        doc_id = upload_data["id"]
        self.assertEqual(upload_data["filename"], "financial_report.pdf")
        self.assertEqual(upload_data["size_bytes"], len(file_content))

        # 2. List documents for User A returns uploaded document immediately
        list_res = self.client.get("/api/documents", headers=headers_a)
        self.assertEqual(list_res.status_code, 200)
        list_data = list_res.json()
        self.assertEqual(list_data["total"], 1)
        self.assertEqual(list_data["documents"][0]["id"], doc_id)

        # 3. User B listing documents returns empty list (tenant isolation)
        headers_b = {"Authorization": f"Bearer {self.token_b}"}
        list_b_res = self.client.get("/api/documents", headers=headers_b)
        self.assertEqual(list_b_res.status_code, 200)
        self.assertEqual(list_b_res.json()["total"], 0)

        # 4. User B trying to access User A's doc details gets 404
        bad_get = self.client.get(f"/api/documents/{doc_id}", headers=headers_b)
        self.assertEqual(bad_get.status_code, 404)

        # 5. User A can download their document
        dl_res = self.client.get(f"/api/documents/{doc_id}/download", headers=headers_a)
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res.content, file_content)

        # 6. User A deletes their document
        del_res = self.client.delete(f"/api/documents/{doc_id}", headers=headers_a)
        self.assertEqual(del_res.status_code, 200)

        # Verify it no longer appears in User A's list
        list_after_del = self.client.get("/api/documents", headers=headers_a)
        self.assertEqual(list_after_del.json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
