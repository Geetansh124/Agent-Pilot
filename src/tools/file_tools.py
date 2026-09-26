"""Thread-isolated workspace file tools backed by centralized persistent storage.

Provides thread-isolated filesystem operations (read, write, list, delete)
delegating persistence to the configured StorageBackend (Google Drive in production).
"""
from __future__ import annotations

import base64
import logging
from typing import Any
from langchain_core.tools import tool

from storage import sanitize_relative_path, sanitize_thread_id, storage

logger = logging.getLogger("tools.file_tools")


@tool
def read_workspace_file(filename: str, thread_id: str = "default") -> dict[str, Any]:
    """Read the text contents of a file in the thread's persistent workspace.

    Args:
        filename: Relative path or name of the file to read (e.g. 'notes.md' or 'reports/summary.txt').
        thread_id: Unique thread identifier scoping the workspace.
    """
    try:
        clean_tid = sanitize_thread_id(thread_id)
        clean_fn = sanitize_relative_path(filename)

        data = storage.download_bytes(category="workspace", thread_id=clean_tid, filename=clean_fn)
        if data is None:
            return {"error": f"File '{filename}' does not exist in workspace.", "filename": filename, "success": False}

        # Size check cap (10MB)
        if len(data) > 10 * 1024 * 1024:
            return {"error": "File exceeds the 10MB read limit.", "filename": filename, "success": False}

        content = data.decode("utf-8", errors="replace")
        return {
            "filename": clean_fn,
            "size_bytes": len(data),
            "content": content,
            "thread_id": clean_tid,
            "storage_backend": storage.backend_name,
            "success": True,
        }
    except PermissionError as exc:
        return {"error": str(exc), "filename": filename, "success": False}
    except Exception as exc:
        logger.warning("Error reading workspace file '%s': %s", filename, exc)
        return {"error": f"Failed to read file: {exc}", "filename": filename, "success": False}


@tool
def write_workspace_file(filename: str, content: str, thread_id: str = "default") -> dict[str, Any]:
    """Write text content to a file in the thread's persistent workspace.

    Args:
        filename: Relative path or name of the file to create or overwrite.
        content: Text content to write into the file.
        thread_id: Unique thread identifier scoping the workspace.
    """
    try:
        clean_tid = sanitize_thread_id(thread_id)
        clean_fn = sanitize_relative_path(filename)
        raw_bytes = content.encode("utf-8")

        if len(raw_bytes) > 20 * 1024 * 1024:
            return {"error": "Content exceeds 20MB write limit.", "filename": filename, "success": False}

        res = storage.upload_bytes(
            category="workspace",
            thread_id=clean_tid,
            filename=clean_fn,
            file_bytes=raw_bytes,
            mime_type="text/plain",
        )
        return {
            "filename": clean_fn,
            "size_bytes": len(raw_bytes),
            "file_id": res.get("file_id"),
            "thread_id": clean_tid,
            "storage_backend": storage.backend_name,
            "success": res.get("success", False),
        }
    except PermissionError as exc:
        return {"error": str(exc), "filename": filename, "success": False}
    except Exception as exc:
        logger.warning("Error writing workspace file '%s': %s", filename, exc)
        return {"error": f"Failed to write file: {exc}", "filename": filename, "success": False}


@tool
def list_workspace_files(thread_id: str = "default") -> dict[str, Any]:
    """List all files stored in the thread's persistent workspace.

    Args:
        thread_id: Unique thread identifier scoping the workspace.
    """
    try:
        clean_tid = sanitize_thread_id(thread_id)
        files = storage.list_files(category="workspace", thread_id=clean_tid)
        return {
            "files": files,
            "total_files": len(files),
            "thread_id": clean_tid,
            "storage_backend": storage.backend_name,
            "success": True,
        }
    except Exception as exc:
        logger.warning("Error listing workspace for thread '%s': %s", thread_id, exc)
        return {"error": f"Failed to list workspace: {exc}", "success": False}


@tool
def delete_workspace_file(filename: str, thread_id: str = "default") -> dict[str, Any]:
    """Delete a file from the thread's persistent workspace.

    Args:
        filename: Relative path or name of the file to delete.
        thread_id: Unique thread identifier scoping the workspace.
    """
    try:
        clean_tid = sanitize_thread_id(thread_id)
        clean_fn = sanitize_relative_path(filename)

        deleted = storage.delete_file(category="workspace", thread_id=clean_tid, filename=clean_fn)
        if not deleted:
            return {"error": f"File '{filename}' does not exist or could not be deleted.", "success": False}

        return {
            "filename": clean_fn,
            "deleted": True,
            "thread_id": clean_tid,
            "storage_backend": storage.backend_name,
            "success": True,
        }
    except PermissionError as exc:
        return {"error": str(exc), "filename": filename, "success": False}
    except Exception as exc:
        logger.warning("Error deleting workspace file '%s': %s", filename, exc)
        return {"error": f"Failed to delete file: {exc}", "filename": filename, "success": False}


@tool
def write_workspace_binary(filename: str, base64_content: str, thread_id: str = "default") -> dict[str, Any]:
    """Write binary content (base64-encoded) to a file in the thread's persistent workspace.

    Args:
        filename: Relative path or name of the binary file to create or overwrite.
        base64_content: Base64-encoded string representing binary content.
        thread_id: Unique thread identifier scoping the workspace.
    """
    try:
        clean_tid = sanitize_thread_id(thread_id)
        clean_fn = sanitize_relative_path(filename)
        file_bytes = base64.b64decode(base64_content)

        res = storage.upload_bytes(
            category="workspace",
            thread_id=clean_tid,
            filename=clean_fn,
            file_bytes=file_bytes,
        )
        return {
            "filename": clean_fn,
            "size_bytes": len(file_bytes),
            "file_id": res.get("file_id"),
            "thread_id": clean_tid,
            "storage_backend": storage.backend_name,
            "success": res.get("success", False),
        }
    except Exception as exc:
        return {"error": f"Failed to write binary file: {exc}", "filename": filename, "success": False}


@tool
def read_workspace_binary(filename: str, thread_id: str = "default") -> dict[str, Any]:
    """Read binary content from a file in the thread's persistent workspace, returned as base64.

    Args:
        filename: Relative path or name of the binary file to read.
        thread_id: Unique thread identifier scoping the workspace.
    """
    try:
        clean_tid = sanitize_thread_id(thread_id)
        clean_fn = sanitize_relative_path(filename)

        data = storage.download_bytes(category="workspace", thread_id=clean_tid, filename=clean_fn)
        if data is None:
            return {"error": f"File '{filename}' does not exist in workspace.", "filename": filename, "success": False}

        return {
            "filename": clean_fn,
            "size_bytes": len(data),
            "base64_content": base64.b64encode(data).decode("ascii"),
            "thread_id": clean_tid,
            "storage_backend": storage.backend_name,
            "success": True,
        }
    except Exception as exc:
        return {"error": f"Failed to read binary file: {exc}", "filename": filename, "success": False}
