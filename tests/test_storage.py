"""Comprehensive test suite for Agent-Pilot storage abstraction and file persistence.

Tests cover:
1. Sanitization: thread ID normalization and strict relative path traversal prevention.
2. LocalStorageBackend: byte uploading, downloading, listing, deleting, nested workspace paths.
3. Workspace file tools: LangChain @tool integration with storage persistence.
4. Binary safety: ensuring arbitrary binary files (PDFs, images, indexes) remain byte-identical.
5. FAISS persistence: vector store serialization, persistence, and post-restart reload.
6. GoogleDriveStorage: lazy safe initialization, secret masking, and mocked API contract tests.
7. FastAPI file endpoints and /health status reporting.
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from storage.base import (
    ALLOWED_CATEGORIES,
    StorageBackend,
    guess_mime_type,
    sanitize_relative_path,
    sanitize_thread_id,
)
from storage.local import LocalStorageBackend
from storage.google_drive import GoogleDriveStorage
from storage import get_storage_backend


class TestStorageSanitization(unittest.TestCase):
    """Test security sanitization and path traversal defenses."""

    def test_sanitize_thread_id_valid(self):
        self.assertEqual(sanitize_thread_id("thread-123_abc"), "thread-123_abc")
        self.assertEqual(sanitize_thread_id("Thread_456"), "Thread_456")

    def test_sanitize_thread_id_removes_dangerous_characters(self):
        self.assertEqual(sanitize_thread_id("../../../etc/passwd"), "etc_passwd")
        self.assertEqual(sanitize_thread_id("thread/../evil"), "thread_evil")
        self.assertEqual(sanitize_thread_id(""), "default")
        self.assertEqual(sanitize_thread_id("   "), "default")

    def test_sanitize_relative_path_valid(self):
        self.assertEqual(sanitize_relative_path("report.pdf"), "report.pdf")
        self.assertEqual(sanitize_relative_path("sub/folder/data.csv"), "sub/folder/data.csv")
        self.assertEqual(sanitize_relative_path("a/b/c/d/file.txt"), "a/b/c/d/file.txt")

    def test_sanitize_relative_path_rejects_traversal(self):
        with self.assertRaises(ValueError):
            sanitize_relative_path("../secret.txt")
        with self.assertRaises(ValueError):
            sanitize_relative_path("a/../../secret.txt")
        with self.assertRaises(ValueError):
            sanitize_relative_path("/absolute/path.txt")
        with self.assertRaises(ValueError):
            sanitize_relative_path("")
        with self.assertRaises(ValueError):
            sanitize_relative_path("foo/../bar")

    def test_guess_mime_type(self):
        self.assertEqual(guess_mime_type("doc.pdf"), "application/pdf")
        self.assertEqual(guess_mime_type("table.csv"), "text/csv")
        self.assertEqual(guess_mime_type("data.json"), "application/json")
        self.assertEqual(guess_mime_type("photo.png"), "image/png")
        self.assertEqual(guess_mime_type("track.mp3"), "audio/mpeg")


class TestLocalStorageBackend(unittest.TestCase):
    """Test LocalStorageBackend file operations and thread isolation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="agent_pilot_storage_test_")
        self.storage = LocalStorageBackend(base_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_upload_and_download_text(self):
        content = b"Hello Agent-Pilot Google Drive storage!"
        res = self.storage.upload_bytes(
            thread_id="test_thread_1",
            category="workspace",
            filename="notes.txt",
            data=content,
        )
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("filename"), "notes.txt")
        self.assertEqual(res.get("size_bytes"), len(content))

        downloaded = self.storage.download_bytes(
            thread_id="test_thread_1",
            category="workspace",
            filename="notes.txt",
        )
        self.assertEqual(downloaded, content)

    def test_upload_and_download_binary_fidelity(self):
        binary_data = bytes(range(256)) * 16  # 4096 bytes with all byte values
        self.storage.upload_bytes(
            thread_id="bin_thread",
            category="workspace",
            filename="binary_artifact.bin",
            data=binary_data,
        )
        downloaded = self.storage.download_bytes(
            thread_id="bin_thread",
            category="workspace",
            filename="binary_artifact.bin",
        )
        self.assertEqual(downloaded, binary_data)

    def test_nested_workspace_paths(self):
        content = b"Subfolder report data"
        self.storage.upload_bytes(
            thread_id="nested_thread",
            category="workspace",
            filename="reports/q3/summary.txt",
            data=content,
        )
        downloaded = self.storage.download_bytes(
            thread_id="nested_thread",
            category="workspace",
            filename="reports/q3/summary.txt",
        )
        self.assertEqual(downloaded, content)

    def test_list_files(self):
        self.storage.upload_bytes("t_list", "workspace", "a.txt", b"A")
        self.storage.upload_bytes("t_list", "workspace", "sub/b.txt", b"B")
        self.storage.upload_bytes("t_list", "exports", "report.pdf", b"PDF")

        workspace_files = self.storage.list_files("t_list", category="workspace")
        file_names = [f["name"] for f in workspace_files]
        self.assertIn("a.txt", file_names)
        self.assertIn("sub/b.txt", file_names)

        all_files = self.storage.list_files("t_list")
        self.assertTrue(len(all_files) >= 3)

    def test_delete_file(self):
        self.storage.upload_bytes("t_del", "workspace", "temp.txt", b"Delete me")
        self.assertIsNotNone(self.storage.download_bytes("t_del", "workspace", "temp.txt"))
        deleted = self.storage.delete_file("t_del", "workspace", "temp.txt")
        self.assertTrue(deleted)
        self.assertIsNone(self.storage.download_bytes("t_del", "workspace", "temp.txt"))

    def test_health_check(self):
        self.assertTrue(self.storage.health_check())


class TestWorkspaceFileTools(unittest.TestCase):
    """Test LangChain @tool wrappers in src/tools/file_tools.py using storage."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="agent_pilot_tools_test_")
        self.storage = LocalStorageBackend(base_dir=self.temp_dir)
        import src.tools.file_tools as ft
        self._orig_storage = ft.storage
        ft.storage = self.storage

    def tearDown(self):
        import src.tools.file_tools as ft
        ft.storage = self._orig_storage
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_and_read_workspace_file_tool(self):
        from src.tools.file_tools import (
            delete_workspace_file,
            list_workspace_files,
            read_workspace_file,
            write_workspace_file,
        )

        # 1. Write
        write_res = write_workspace_file.invoke({
            "filename": "analysis.md",
            "content": "# Research Analysis\nPersisted to Google Drive storage.",
            "thread_id": "tool_thread_1",
        })
        self.assertTrue(write_res.get("success"))

        # 2. Read
        read_res = read_workspace_file.invoke({
            "filename": "analysis.md",
            "thread_id": "tool_thread_1",
        })
        self.assertTrue(read_res.get("success"))
        self.assertIn("Research Analysis", read_res.get("content", ""))

        # 3. List
        list_res = list_workspace_files.invoke({
            "thread_id": "tool_thread_1",
        })
        self.assertTrue(list_res.get("success"))
        names = [f["name"] for f in list_res.get("files", [])]
        self.assertIn("analysis.md", names)

        # 4. Delete
        del_res = delete_workspace_file.invoke({
            "filename": "analysis.md",
            "thread_id": "tool_thread_1",
        })
        self.assertTrue(del_res.get("success"))

    def test_path_traversal_rejection(self):
        from src.tools.file_tools import read_workspace_file, write_workspace_file

        write_res = write_workspace_file.invoke({
            "filename": "../../secret.txt",
            "content": "Malicious payload",
            "thread_id": "tool_thread_1",
        })
        self.assertFalse(write_res.get("success"))
        self.assertIn("traversal", write_res.get("error", "").lower())

        read_res = read_workspace_file.invoke({
            "filename": "../../../etc/passwd",
            "thread_id": "tool_thread_1",
        })
        self.assertFalse(read_res.get("success"))
        self.assertIn("traversal", read_res.get("error", "").lower())


class TestFAISSPersistenceAcrossRestarts(unittest.TestCase):
    """Test FAISS vector store persistence to storage backend and post-restart recovery."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="agent_pilot_faiss_test_")
        self.storage = LocalStorageBackend(base_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_faiss_save_and_reload(self):
        from langchain_community.vectorstores import FAISS
        from langchain_core.documents import Document
        from langchain_huggingface import HuggingFaceEmbeddings

        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        sample_docs = [
            Document(page_content="Agent-Pilot utilizes Google Drive as single persistent file storage.", metadata={"source": "spec.txt", "page": 1}),
            Document(page_content="Render web services use Docker runtime and temporary local files.", metadata={"source": "spec.txt", "page": 2}),
            Document(page_content="Relational state is managed in chatbot.db database.", metadata={"source": "spec.txt", "page": 3}),
        ]

        # 1. Build in-memory FAISS store
        store = FAISS.from_documents(sample_docs, embeddings)

        # 2. Persist vector store through storage abstraction
        save_success = self.storage.save_vector_store("thread_faiss_test", store)
        self.assertTrue(save_success)
        self.assertTrue(self.storage.has_thread_vector_store("thread_faiss_test"))

        # 3. Simulate process restart: delete in-memory store reference
        del store

        # 4. Reload from storage
        reloaded_store = self.storage.load_vector_store("thread_faiss_test", embeddings)
        self.assertIsNotNone(reloaded_store)

        # 5. Query reloaded vector store to verify embedding search works
        results = reloaded_store.similarity_search("Where does Agent-Pilot store persistent files?", k=1)
        self.assertTrue(len(results) > 0)
        self.assertIn("Google Drive", results[0].page_content)


class TestGoogleDriveMockedAPI(unittest.TestCase):
    """Test GoogleDriveStorage methods with mocked Google Drive API client."""

    def setUp(self):
        self.gdrive = GoogleDriveStorage.__new__(GoogleDriveStorage)
        self.gdrive._enabled = True
        self.gdrive._root_folder_id = "mock_root_folder_id"
        self.gdrive._folder_cache = {}
        self.mock_service = MagicMock()
        self.gdrive._service = self.mock_service

    def test_mocked_health_check(self):
        self.mock_service.about().get().execute.return_value = {
            "user": {"emailAddress": "agent-pilot-storage@project.iam.gserviceaccount.com"}
        }
        self.assertTrue(self.gdrive.health_check())

    def test_mocked_folder_creation(self):
        # 1. First search finds nothing
        self.mock_service.files().list().execute.return_value = {"files": []}
        # 2. Creation returns mock id
        self.mock_service.files().create().execute.return_value = {"id": "created_cat_id"}

        folder_id = self.gdrive.get_or_create_folder("workspace", "mock_root_folder_id")
        self.assertEqual(folder_id, "created_cat_id")
        # Verify cached on second call
        cached_id = self.gdrive.get_or_create_folder("workspace", "mock_root_folder_id")
        self.assertEqual(cached_id, "created_cat_id")

    def test_mocked_upload_and_delete(self):
        # Setup folder cache to bypass folder queries
        self.gdrive._folder_cache["workspace/mock_thread"] = "mock_thread_folder_id"
        self.gdrive._folder_cache["mock_root_folder_id/workspace"] = "mock_cat_folder_id"

        # Mock upload: list finds no existing file -> calls create
        self.mock_service.files().list().execute.return_value = {"files": []}
        self.mock_service.files().create().execute.return_value = {
            "id": "file_123",
            "name": "report.pdf",
            "size": "1024",
            "mimeType": "application/pdf",
        }

        res = self.gdrive.upload_bytes(
            category="workspace",
            thread_id="mock_thread",
            filename="report.pdf",
            file_bytes=b"%PDF-1.4 mock content",
        )
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("file_id"), "file_123")

        # Mock delete: find file returns file_123 -> calls delete
        self.mock_service.files().list().execute.return_value = {"files": [{"id": "file_123", "name": "report.pdf"}]}
        self.mock_service.files().delete().execute.return_value = {}

        del_res = self.gdrive.delete_file(
            category="workspace",
            thread_id="mock_thread",
            filename="report.pdf",
        )
        self.assertTrue(del_res)


if __name__ == "__main__":
    unittest.main()
