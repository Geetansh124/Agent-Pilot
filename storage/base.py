"""Storage backend base abstraction and path sanitization.

Provides unified interface for persistent application files (Google Drive, AWS, Local)
and enforces thread isolation, path traversal guards, and deterministic folder structures.
"""
from __future__ import annotations

import mimetypes
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

ALLOWED_CATEGORIES = frozenset({"documents", "workspace", "vectors", "exports", "attachments", "audio", "database", "memory"})


class StoragePathError(ValueError, PermissionError):
    """Raised when a storage path violates safety boundaries or attempts directory traversal."""
    pass


def sanitize_thread_id(thread_id: str | None) -> str:
    """Normalize and sanitize a thread identifier to prevent directory traversal."""
    if not thread_id:
        return "default"
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(thread_id).strip())
    clean = re.sub(r"_+", "_", clean).strip("_")
    if not clean or clean in (".", ".."):
        return "default"
    return clean[:64]


def sanitize_relative_path(path_str: str) -> str:
    """Normalize a relative file path and prevent directory traversal breakout."""
    if not path_str or not isinstance(path_str, str):
        raise StoragePathError("File path cannot be empty.")

    # Normalize backslashes and strip whitespace
    normalized = path_str.replace("\\", "/").strip()
    if normalized.startswith("/"):
        raise StoragePathError(f"Access denied: Absolute path '{path_str}' is forbidden.")

    # Reject directory traversal attempts
    segments = [s.strip() for s in normalized.split("/") if s.strip()]
    if not segments:
        raise StoragePathError("File path cannot be empty after normalization.")

    for segment in segments:
        if segment in ("..", "."):
            raise StoragePathError(f"Access denied: Path '{path_str}' attempts directory traversal.")

    return "/".join(segments)


def resolve_category_and_thread(
    *candidates: Any,
    default_category: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """Resolve category and thread_id flexibly from any combination of args/kwargs."""
    cat = None
    tid = None

    for val in candidates:
        if val is None:
            continue
        s = str(val).strip()
        if not s:
            continue
        if s.lower() in ALLOWED_CATEGORIES and cat is None:
            cat = s.lower()
        elif tid is None and s.lower() not in ALLOWED_CATEGORIES:
            tid = s

    if cat is None and default_category:
        cat = default_category
    return cat, sanitize_thread_id(tid)


def guess_mime_type(filename: str) -> str:
    """Guess MIME type from filename with fallbacks for common project artifacts."""
    fn_lower = filename.lower()
    if fn_lower.endswith(".pdf"):
        return "application/pdf"
    elif fn_lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif fn_lower.endswith(".json"):
        return "application/json"
    elif fn_lower.endswith(".csv"):
        return "text/csv"
    elif fn_lower.endswith((".md", ".markdown")):
        return "text/markdown"
    elif fn_lower.endswith(".txt"):
        return "text/plain"
    elif fn_lower.endswith(".wav"):
        return "audio/wav"
    elif fn_lower.endswith(".mp3"):
        return "audio/mpeg"
    elif fn_lower.endswith((".faiss", ".pkl")):
        return "application/octet-stream"

    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


class StorageBackend(ABC):
    """Abstract base class for all persistent file storage providers."""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Indicate whether the backend is active, authenticated, and reachable."""
        pass

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Identifier of the backend implementation (google_drive, aws, local)."""
        pass

    @abstractmethod
    def save_document(
        self,
        thread_id: str,
        filename: str,
        file_bytes: bytes,
        vector_store: Any = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Save raw document bytes, optional vector index, and metadata."""
        pass

    @abstractmethod
    def load_document_metadata(self, thread_id: str) -> dict[str, Any]:
        """Load document metadata for a thread."""
        pass

    @abstractmethod
    def save_vector_store(self, thread_id: str, vector_store: Any) -> bool:
        """Persist FAISS vector-store artifacts (index.faiss and index.pkl)."""
        pass

    @abstractmethod
    def load_vector_store(self, thread_id: str, embeddings: Any) -> Optional[Any]:
        """Download and load FAISS vector store for a thread."""
        pass

    @abstractmethod
    def has_thread_vector_store(self, thread_id: str) -> bool:
        """Check if vector store artifacts exist for the thread."""
        pass

    @abstractmethod
    def upload_bytes(
        self,
        category: str,
        thread_id: str,
        filename: str,
        file_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
        data: Optional[bytes] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Upload raw bytes into a thread's category folder."""
        pass

    @abstractmethod
    def download_bytes(
        self,
        category: str,
        thread_id: str,
        filename: str,
        **kwargs: Any,
    ) -> Optional[bytes]:
        """Download raw bytes from a thread's category folder."""
        pass

    @abstractmethod
    def delete_file(
        self,
        category: str,
        thread_id: str,
        filename: str,
        **kwargs: Any,
    ) -> bool:
        """Delete a file from a thread's category folder."""
        pass

    @abstractmethod
    def list_files(
        self,
        category: Optional[str] = None,
        thread_id: Optional[str] = None,
        prefix: str = "",
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """List files registered under a thread's category folder or across all categories."""
        pass

    @abstractmethod
    def find_file(
        self,
        category: str,
        thread_id: str,
        filename: str,
    ) -> Optional[dict[str, Any]]:
        """Find a file and return its metadata dict."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check connectivity and operational readiness of the storage provider."""
        pass

    def save_user_document(
        self,
        user_id: str,
        doc_id: str,
        filename: str,
        file_bytes: bytes,
        mime_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Save a user-scoped document under users/{user_id}/documents/{doc_id}/."""
        # Default fallback delegates to category upload
        rel_path = f"users/{sanitize_thread_id(user_id)}/documents/{sanitize_thread_id(doc_id)}/{filename}"
        res = self.upload_bytes("documents", user_id, rel_path, file_bytes, mime_type=mime_type)
        return {
            "doc_id": doc_id,
            "user_id": user_id,
            "filename": filename,
            "file_id": res.get("file_id"),
            "drive_file_id": res.get("file_id"),
            "web_view_link": res.get("web_view_link"),
            "size_bytes": len(file_bytes),
            "mime_type": mime_type or guess_mime_type(filename),
            "success": res.get("success", True),
        }

    def load_user_document_bytes(
        self,
        user_id: str,
        doc_id: str,
        filename: str,
    ) -> Optional[bytes]:
        """Download raw bytes of a user document."""
        rel_path = f"users/{sanitize_thread_id(user_id)}/documents/{sanitize_thread_id(doc_id)}/{filename}"
        return self.download_bytes("documents", user_id, rel_path)

    def has_user_document(
        self,
        user_id: str,
        doc_id: str,
        filename: str,
    ) -> bool:
        """Check whether user document exists in storage."""
        return False

    def delete_user_document(
        self,
        user_id: str,
        doc_id: str,
        filename: Optional[str] = None,
    ) -> bool:
        """Delete a user document from storage."""
        if filename:
            rel_path = f"users/{sanitize_thread_id(user_id)}/documents/{sanitize_thread_id(doc_id)}/{filename}"
            return self.delete_file("documents", user_id, rel_path)
        return True

    def save_user_vector_store(self, user_id: str, doc_id: str, vector_store: Any) -> bool:
        """Persist FAISS index artifacts under users/{user_id}/vectors/{doc_id}/."""
        return False

    def load_user_vector_store(self, user_id: str, doc_id: str, embeddings: Any) -> Optional[Any]:
        """Download and reconstruct FAISS index from users/{user_id}/vectors/{doc_id}/."""
        return None

    def has_user_vector_store(self, user_id: str, doc_id: str) -> bool:
        """Check whether vector store exists under users/{user_id}/vectors/{doc_id}/."""
        return False
