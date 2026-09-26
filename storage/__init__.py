"""Unified storage layer for Agent-Pilot.

Provides single persistent storage abstraction backing documents, workspace files,
vector stores, and exports with Google Drive as primary production backend.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from storage.base import (
    ALLOWED_CATEGORIES,
    StorageBackend,
    guess_mime_type,
    sanitize_relative_path,
    sanitize_thread_id,
)
from storage.local import LocalStorageBackend

logger = logging.getLogger("storage")

_ACTIVE_BACKEND: Optional[StorageBackend] = None


def get_storage_backend() -> StorageBackend:
    """Resolve and initialize active StorageBackend according to STORAGE_BACKEND env variable."""
    global _ACTIVE_BACKEND
    if _ACTIVE_BACKEND is not None:
        return _ACTIVE_BACKEND

    backend_type = os.getenv("STORAGE_BACKEND", "google_drive").lower().strip()

    if backend_type == "google_drive":
        try:
            from storage.google_drive import GoogleDriveStorage

            drive_inst = GoogleDriveStorage()
            if drive_inst.enabled:
                _ACTIVE_BACKEND = drive_inst
                return _ACTIVE_BACKEND
            logger.info("Google Drive storage not configured with credentials; using local fallback.")
        except Exception as exc:
            logger.warning("Google Drive storage initialization error: %s; using local fallback.", exc)
        _ACTIVE_BACKEND = LocalStorageBackend()
        return _ACTIVE_BACKEND

    elif backend_type == "aws":
        try:
            from storage.aws import AWSStorageBackend

            aws_inst = AWSStorageBackend()
            if aws_inst.enabled:
                _ACTIVE_BACKEND = aws_inst
                return _ACTIVE_BACKEND
            logger.info("AWS storage not configured with credentials; using local fallback.")
        except Exception as exc:
            logger.warning("AWS storage initialization error: %s; using local fallback.", exc)
        _ACTIVE_BACKEND = LocalStorageBackend()
        return _ACTIVE_BACKEND

    elif backend_type in ("none", "local"):
        _ACTIVE_BACKEND = LocalStorageBackend()
        return _ACTIVE_BACKEND

    else:
        logger.warning("Unrecognized STORAGE_BACKEND '%s'; falling back to local storage.", backend_type)
        _ACTIVE_BACKEND = LocalStorageBackend()
        return _ACTIVE_BACKEND


def reset_storage_backend() -> None:
    """Reset cached singleton (primarily used for unit testing across backends)."""
    global _ACTIVE_BACKEND
    _ACTIVE_BACKEND = None


# Public singleton instance
storage = get_storage_backend()

__all__ = [
    "StorageBackend",
    "LocalStorageBackend",
    "get_storage_backend",
    "reset_storage_backend",
    "storage",
    "sanitize_thread_id",
    "sanitize_relative_path",
    "guess_mime_type",
    "ALLOWED_CATEGORIES",
]
