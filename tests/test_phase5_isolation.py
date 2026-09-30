"""Automated Multi-Tenant Isolation and Penetration Tests for Phase 5.

Verifies strict cross-tenant isolation across document catalogs, direct lookups,
file downloads, document deletions, thread attachments, vector embeddings,
and storage partitions.
"""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.embeddings import FakeEmbeddings
from langchain_community.vectorstores import FAISS

from src.auth.auth import create_access_token
from src.auth.database import (
    create_user,
    get_user_document,
    init_auth_db,
    list_user_documents,
)
from src.storage.routes import documents_router
from storage.local import LocalStorageBackend


class TestMultiTenantIsolation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "isolation_test.db")
        self.storage_dir = os.path.join(self.temp_dir.name, "storage")
        os.makedirs(self.storage_dir, exist_ok=True)

        self._orig_env_db = os.environ.get("CHATBOT_DB_PATH")
        os.environ["CHATBOT_DB_PATH"] = self.db_path
        init_auth_db(self.db_path)

        self.storage_backend = LocalStorageBackend(base_dir=self.storage_dir)

        import storage as storage_mod
        import src.storage.routes as routes_mod
        self._orig_storage = storage_mod.storage
        storage_mod.storage = self.storage_backend
        routes_mod.storage = self.storage_backend

        self.fake_embeddings = FakeEmbeddings(size=384)
        self.patcher = patch("langraph_rag_backend.get_embeddings", return_value=self.fake_embeddings)
        self.patcher.start()

        self.app = FastAPI()
        self.app.include_router(documents_router, prefix="/api")
        self.client = TestClient(self.app)

        # Create two distinct test users (Tenants)
        self.tenant_a = create_user("tenant_alpha@company.com", "PasswordAlpha123!", "Tenant Alpha", db_path=self.db_path)
        self.tenant_b = create_user("tenant_beta@company.com", "PasswordBeta123!", "Tenant Beta", db_path=self.db_path)

        self.token_a = create_access_token(self.tenant_a["id"], role="user")
        self.token_b = create_access_token(self.tenant_b["id"], role="user")
        self.headers_a = {"Authorization": f"Bearer {self.token_a}"}
        self.headers_b = {"Authorization": f"Bearer {self.token_b}"}

    def tearDown(self):
        import gc
        import storage as storage_mod
        import src.storage.routes as routes_mod

        self.patcher.stop()
        storage_mod.storage = self._orig_storage
        routes_mod.storage = self._orig_storage

        if self._orig_env_db:
            os.environ["CHATBOT_DB_PATH"] = self._orig_env_db
        else:
            os.environ.pop("CHATBOT_DB_PATH", None)

        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_catalog_listing_isolation(self):
        """User A and User B cannot see each other's documents in /api/documents."""
        doc_a_bytes = b"Confidential Project Alpha Specifications"
        files_a = {"file": ("alpha_spec.txt", io.BytesIO(doc_a_bytes), "text/plain")}
        res_a = self.client.post("/api/documents/upload", files=files_a, headers=self.headers_a)
        self.assertEqual(res_a.status_code, 201)

        doc_b_bytes = b"Proprietary Project Beta Financials"
        files_b = {"file": ("beta_fin.txt", io.BytesIO(doc_b_bytes), "text/plain")}
        res_b = self.client.post("/api/documents/upload", files=files_b, headers=self.headers_b)
        self.assertEqual(res_b.status_code, 201)

        # Tenant A lists documents
        catalog_a = self.client.get("/api/documents", headers=self.headers_a).json()
        filenames_a = [d["filename"] for d in catalog_a["documents"]]
        self.assertIn("alpha_spec.txt", filenames_a)
        self.assertNotIn("beta_fin.txt", filenames_a)

        # Tenant B lists documents
        catalog_b = self.client.get("/api/documents", headers=self.headers_b).json()
        filenames_b = [d["filename"] for d in catalog_b["documents"]]
        self.assertIn("beta_fin.txt", filenames_b)
        self.assertNotIn("alpha_spec.txt", filenames_b)

    def test_direct_document_lookup_blocked(self):
        """Direct GET /api/documents/{doc_id} of another tenant returns 404."""
        files = {"file": ("secret_alpha.txt", io.BytesIO(b"Secret Alpha Data"), "text/plain")}
        upload = self.client.post("/api/documents/upload", files=files, headers=self.headers_a).json()
        doc_a_id = upload["id"]

        # Tenant A can access
        lookup_a = self.client.get(f"/api/documents/{doc_a_id}", headers=self.headers_a)
        self.assertEqual(lookup_a.status_code, 200)

        # Tenant B is blocked with 404
        lookup_b = self.client.get(f"/api/documents/{doc_a_id}", headers=self.headers_b)
        self.assertEqual(lookup_b.status_code, 404)
        self.assertIn("not found or access denied", lookup_b.json()["detail"].lower())

    def test_document_download_blocked(self):
        """Tenant B cannot download Tenant A's document binary bytes."""
        files = {"file": ("payroll.csv", io.BytesIO(b"Name,Salary\nAlice,120000"), "text/csv")}
        upload = self.client.post("/api/documents/upload", files=files, headers=self.headers_a).json()
        doc_a_id = upload["id"]

        # Tenant A can download
        download_a = self.client.get(f"/api/documents/{doc_a_id}/download", headers=self.headers_a)
        self.assertEqual(download_a.status_code, 200)
        self.assertIn(b"Alice,120000", download_a.content)

        # Tenant B is blocked with 404
        download_b = self.client.get(f"/api/documents/{doc_a_id}/download", headers=self.headers_b)
        self.assertEqual(download_b.status_code, 404)

    def test_document_deletion_blocked(self):
        """Tenant B cannot delete Tenant A's document."""
        files = {"file": ("legal_contract.pdf", io.BytesIO(b"%PDF-1.4 contract content"), "application/pdf")}
        upload = self.client.post("/api/documents/upload", files=files, headers=self.headers_a).json()
        doc_a_id = upload["id"]

        # Tenant B attempts deletion -> 404
        delete_attempt = self.client.delete(f"/api/documents/{doc_a_id}", headers=self.headers_b)
        self.assertEqual(delete_attempt.status_code, 404)

        # Verify document is still intact for Tenant A
        check_a = self.client.get(f"/api/documents/{doc_a_id}", headers=self.headers_a)
        self.assertEqual(check_a.status_code, 200)

    def test_thread_attachment_and_active_document_isolation(self):
        """Tenant B cannot attach Tenant A's document or view Tenant A's active thread document."""
        files = {"file": ("strategy.txt", io.BytesIO(b"Strategic market expansion plan."), "text/plain")}
        upload = self.client.post("/api/documents/upload", files=files, headers=self.headers_a).json()
        doc_a_id = upload["id"]

        # Tenant A attaches to thread-alpha
        attach_a = self.client.post(f"/api/threads/thread-alpha/documents/{doc_a_id}/attach", headers=self.headers_a)
        self.assertEqual(attach_a.status_code, 200)

        # Tenant B attempts to attach Tenant A's document to thread-beta -> 404
        attach_b = self.client.post(f"/api/threads/thread-beta/documents/{doc_a_id}/attach", headers=self.headers_b)
        self.assertEqual(attach_b.status_code, 404)

        # Tenant A checks active document on thread-alpha -> attached
        active_a = self.client.get("/api/threads/thread-alpha/document", headers=self.headers_a).json()
        self.assertTrue(active_a["attached"])
        self.assertEqual(active_a["document"]["id"], doc_a_id)

        # Tenant B checks active document on thread-alpha -> returns not attached (scoped to B)
        active_b = self.client.get("/api/threads/thread-alpha/document", headers=self.headers_b).json()
        self.assertFalse(active_b["attached"])
        self.assertIsNone(active_b["document"])

    def test_storage_backend_partition_isolation(self):
        """Direct storage queries assert physical folder partition isolation."""
        docs = [Document(page_content="Private Tenant Alpha Partition", metadata={"source": "priv.txt"})]
        store_a = FAISS.from_documents(docs, self.fake_embeddings)

        self.storage_backend.save_user_document(
            user_id=self.tenant_a["id"],
            doc_id="doc-part-1",
            filename="priv.txt",
            file_bytes=b"Private Content",
        )
        self.storage_backend.save_user_vector_store(
            user_id=self.tenant_a["id"],
            doc_id="doc-part-1",
            vector_store=store_a,
        )

        # Tenant A partition has document and vector store
        self.assertTrue(self.storage_backend.has_user_document(self.tenant_a["id"], "doc-part-1", "priv.txt"))
        self.assertTrue(self.storage_backend.has_user_vector_store(self.tenant_a["id"], "doc-part-1"))

        # Tenant B partition has NO presence
        self.assertFalse(self.storage_backend.has_user_document(self.tenant_b["id"], "doc-part-1", "priv.txt"))
        self.assertFalse(self.storage_backend.has_user_vector_store(self.tenant_b["id"], "doc-part-1"))
        self.assertIsNone(self.storage_backend.load_user_document_bytes(self.tenant_b["id"], "doc-part-1", "priv.txt"))
        self.assertIsNone(self.storage_backend.load_user_vector_store(self.tenant_b["id"], "doc-part-1", self.fake_embeddings))


if __name__ == "__main__":
    unittest.main()
