"""Session JSONL manifest, storage synchronization, and checksum verification."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from typing import Any, Optional

from src.harness.config import get_harness_settings
from storage import storage

logger = logging.getLogger("harness.sync")


def compute_sha256(filepath: str) -> str:
    """Compute SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class SessionSyncManager:
    """Synchronizes harness JSONL sessions and manifests to persistent storage."""

    def __init__(self, storage_backend: Any = None):
        self.storage = storage_backend if storage_backend is not None else storage
        self.settings = get_harness_settings()

    def get_session_paths(self, user_id: str, thread_id: str) -> tuple[str, str]:
        """Return paths to local session.jsonl and manifest.json."""
        ws = self.settings.get_thread_workspace(user_id, thread_id)
        os.makedirs(ws, exist_ok=True)
        jsonl_path = os.path.join(ws, "session.jsonl")
        manifest_path = os.path.join(ws, "manifest.json")
        return jsonl_path, manifest_path

    def write_manifest(self, user_id: str, thread_id: str, last_seq: int = 0) -> dict[str, Any]:
        """Create or update manifest with file size and SHA-256 digest."""
        jsonl_path, manifest_path = self.get_session_paths(user_id, thread_id)
        if not os.path.exists(jsonl_path):
            with open(jsonl_path, "w", encoding="utf-8") as f:
                f.write("")

        sha = compute_sha256(jsonl_path)
        size = os.path.getsize(jsonl_path)

        manifest = {
            "session_id": f"ap-{thread_id}",
            "thread_id": thread_id,
            "format_version": "1.0",
            "sha256": sha,
            "size_bytes": size,
            "last_seq": last_seq,
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        return manifest

    def verify_manifest(self, user_id: str, thread_id: str) -> bool:
        """Verify checksum integrity of session.jsonl against manifest.json."""
        jsonl_path, manifest_path = self.get_session_paths(user_id, thread_id)
        if not os.path.exists(jsonl_path) or not os.path.exists(manifest_path):
            return False

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            expected_sha = manifest.get("sha256")
            actual_sha = compute_sha256(jsonl_path)
            return actual_sha == expected_sha
        except Exception as exc:
            logger.warning("Manifest verification failed for thread %s: %s", thread_id, exc)
            return False

    def sync_to_storage(self, user_id: str, thread_id: str) -> bool:
        """Push local session JSONL and manifest to configured storage backend."""
        if not getattr(self.storage, "enabled", False):
            return True

        jsonl_path, manifest_path = self.get_session_paths(user_id, thread_id)
        try:
            if os.path.exists(jsonl_path) and hasattr(self.storage, "upload_bytes"):
                with open(jsonl_path, "rb") as f:
                    self.storage.upload_bytes(thread_id, "harness_session", "session.jsonl", f.read())
            if os.path.exists(manifest_path) and hasattr(self.storage, "upload_bytes"):
                with open(manifest_path, "rb") as f:
                    self.storage.upload_bytes(thread_id, "harness_session", "manifest.json", f.read())
            return True
        except Exception as exc:
            logger.error("Failed to sync harness session to storage for %s: %s", thread_id, exc)
            return False

    def restore_from_storage(self, user_id: str, thread_id: str) -> bool:
        """Pull remote session JSONL and manifest into a clean tenant workspace."""
        if not getattr(self.storage, "enabled", False):
            return False

        jsonl_path, manifest_path = self.get_session_paths(user_id, thread_id)
        try:
            if hasattr(self.storage, "download_bytes"):
                jsonl_bytes = self.storage.download_bytes(thread_id, "harness_session", "session.jsonl")
                manifest_bytes = self.storage.download_bytes(thread_id, "harness_session", "manifest.json")
                if jsonl_bytes is not None and manifest_bytes is not None:
                    with open(jsonl_path, "wb") as f:
                        f.write(jsonl_bytes)
                    with open(manifest_path, "wb") as f:
                        f.write(manifest_bytes)
                    return self.verify_manifest(user_id, thread_id)
            return False
        except Exception as exc:
            logger.error("Failed to restore harness session for %s: %s", thread_id, exc)
            return False

