"""Unit and integration tests for Phase 3: Multi-Tenant Vector RAG Pipeline."""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.embeddings import FakeEmbeddings
from langchain_community.vectorstores import FAISS

from src.auth.auth import create_access_token
from src.auth.database import (
    create_user,
    get_thread_active_document,
    init_auth_db,
)
from src.rag import multi_doc_manager
from src.storage.routes import documents_router
from storage.local import LocalStorageBackend


class TestPhase3VectorRAG(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_chatbot.db")
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

        # Patch get_embeddings in langraph_rag_backend to use FakeEmbeddings for fast testing
        self.patcher = patch("langraph_rag_backend.get_embeddings", return_value=self.fake_embeddings)
        self.mock_get_embeddings = self.patcher.start()

        self.app = FastAPI()
        self.app.include_router(documents_router, prefix="/api")
        self.client = TestClient(self.app)

        self.user_a = create_user("alice_rag@example.com", "Password123!", "Alice RAG", db_path=self.db_path)
        self.user_b = create_user("bob_rag@example.com", "Password123!", "Bob RAG", db_path=self.db_path)

        self.token_a = create_access_token(self.user_a["id"], role="user")
        self.token_b = create_access_token(self.user_b["id"], role="user")
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

    def test_user_scoped_vector_persistence_and_isolation(self):
        """Test vector store persists to user-scoped path and respects tenant isolation."""
        docs = [
            Document(page_content="Agent-Pilot autonomous agent platform.", metadata={"source": "overview.md", "page": 1}),
            Document(page_content="Multi-tenant cloud architecture using Google Drive.", metadata={"source": "overview.md", "page": 2}),
        ]
        store = FAISS.from_documents(docs, self.fake_embeddings)

        # Save store under User A
        self.storage_backend.save_user_vector_store(
            user_id=self.user_a["id"],
            doc_id="doc-xyz",
            vector_store=store,
        )

        # User A has vector store
        self.assertTrue(self.storage_backend.has_user_vector_store(self.user_a["id"], "doc-xyz"))
        # User B does NOT have access or presence
        self.assertFalse(self.storage_backend.has_user_vector_store(self.user_b["id"], "doc-xyz"))

        # Load back for User A
        loaded_store = self.storage_backend.load_user_vector_store(
            user_id=self.user_a["id"],
            doc_id="doc-xyz",
            embeddings=self.fake_embeddings,
        )
        self.assertIsNotNone(loaded_store)
        results = loaded_store.similarity_search("autonomous platform", k=2)
        self.assertGreater(len(results), 0)
        retrieved_texts = [r.page_content for r in results]
        self.assertTrue(any("Agent-Pilot" in t for t in retrieved_texts))

    def test_upload_and_attach_document_to_thread(self):
        """Test document upload automatically creates vector embeddings and attaches to thread."""
        sample_text = b"Agent-Pilot integrates RuVector, hybrid search, and persistent cloud storage."
        files = {"file": ("manual.txt", io.BytesIO(sample_text), "text/plain")}
        data = {"thread_id": "thread-101"}

        resp = self.client.post("/api/documents/upload", files=files, data=data, headers=self.headers_a)
        self.assertEqual(resp.status_code, 201)
        payload = resp.json()
        doc_id = payload["id"]
        self.assertEqual(payload["filename"], "manual.txt")
        self.assertGreater(payload["chunks"], 0)

        # Verify vector store persisted
        self.assertTrue(self.storage_backend.has_user_vector_store(self.user_a["id"], doc_id))

        # Query active thread document
        doc_resp = self.client.get("/api/threads/thread-101/document", headers=self.headers_a)
        self.assertEqual(doc_resp.status_code, 200)
        doc_data = doc_resp.json()
        self.assertTrue(doc_data["attached"])
        self.assertEqual(doc_data["document"]["doc_id"], doc_id)

    def test_attach_historical_document_and_on_demand_warmup(self):
        """Test user can attach any historical document from catalog and warm up cache."""
        sample_doc = b"Cloud native microservices scale independently on Google Cloud."
        files = {"file": ("cloud.txt", io.BytesIO(sample_doc), "text/plain")}

        # 1. Upload without thread_id
        upload_resp = self.client.post("/api/documents/upload", files=files, headers=self.headers_a)
        self.assertEqual(upload_resp.status_code, 201)
        doc_id = upload_resp.json()["id"]

        # 2. Check thread before attach
        check_before = self.client.get("/api/threads/thread-202/document", headers=self.headers_a)
        self.assertEqual(check_before.status_code, 200)
        self.assertFalse(check_before.json()["attached"])

        # 3. Attach historical document
        attach_resp = self.client.post(
            f"/api/threads/thread-202/documents/{doc_id}/attach",
            headers=self.headers_a,
        )
        self.assertEqual(attach_resp.status_code, 200)
        self.assertEqual(attach_resp.json()["status"], "attached")

        # 4. Check active document now attached
        check_after = self.client.get("/api/threads/thread-202/document", headers=self.headers_a)
        self.assertTrue(check_after.json()["attached"])
        self.assertEqual(check_after.json()["document"]["filename"], "cloud.txt")

        # 5. Clear in-memory multi_doc_manager to simulate server restart / cache eviction
        multi_doc_manager.remove_thread("thread-202")
        self.assertFalse(multi_doc_manager.has_documents("thread-202"))

        # 6. On-demand restoration via get_or_restore_retriever
        retriever = multi_doc_manager.get_or_restore_retriever(
            "thread-202",
            embeddings=self.fake_embeddings,
            storage_backend=self.storage_backend,
        )
        self.assertIsNotNone(retriever)
        results = retriever.retrieve("microservices Google Cloud", k=1)
        self.assertGreater(len(results), 0)
        self.assertIn("cloud.txt", results[0]["citation"])

    def test_cross_tenant_attach_blocked(self):
        """Test User B cannot attach or access User A's persistent document (HTTP 404)."""
        sample_text = b"Confidential financial statement for Alice."
        files = {"file": ("confidential.txt", io.BytesIO(sample_text), "text/plain")}

        # Upload as User A
        upload_resp = self.client.post("/api/documents/upload", files=files, headers=self.headers_a)
        self.assertEqual(upload_resp.status_code, 201)
        user_a_doc_id = upload_resp.json()["id"]

        # User B attempts to attach User A's document to User B's thread
        attach_resp = self.client.post(
            f"/api/threads/thread-bob/documents/{user_a_doc_id}/attach",
            headers=self.headers_b,
        )
        self.assertEqual(attach_resp.status_code, 404)
        self.assertIn("not found or access denied", attach_resp.json()["detail"].lower())

    def test_grounded_qa_retrieval_citations(self):
        """Test RAG retrieval returns grounded citations with filename and provenance."""
        sample_text = b"Ruflo Swarm implements hierarchical and mesh coordination loops for AI agents."
        files = {"file": ("ruflo_specs.txt", io.BytesIO(sample_text), "text/plain")}

        upload_resp = self.client.post("/api/documents/upload", files=files, headers=self.headers_a)
        doc_id = upload_resp.json()["id"]

        # Attach to thread-303
        self.client.post(f"/api/threads/thread-303/documents/{doc_id}/attach", headers=self.headers_a)

        # Call rag_tool from langraph_rag_backend
        from langraph_rag_backend import rag_tool
        result = rag_tool.invoke({"query": "hierarchical mesh coordination", "thread_id": "thread-303"})

        self.assertIn("citations", result)
        self.assertGreater(len(result["citations"]), 0)
        self.assertTrue(any("ruflo_specs.txt" in c for c in result["citations"]))
        self.assertIn("context", result)
        self.assertTrue(any("coordination loops" in c for c in result["context"]))


if __name__ == "__main__":
    unittest.main()
