"""Sandboxed workspace file tools.

Provides thread-isolated filesystem operations (read, write, list, delete)
with strict path traversal guards prohibiting breakout of the thread workspace.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from langchain_core.tools import tool

BASE_WORKSPACE_DIR = Path("workspaces").resolve()


def _get_sandboxed_path(filename: str, thread_id: str) -> Path:
    """Resolve and validate a sandboxed path within the thread workspace."""
    clean_tid = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(thread_id).strip()) or "default"
    thread_dir = (BASE_WORKSPACE_DIR / clean_tid).resolve()
    thread_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize and resolve file target
    target = (thread_dir / filename).resolve()
    if not str(target).startswith(str(thread_dir)):
        raise PermissionError(f"Access denied: path '{filename}' attempts directory traversal.")
    return target


@tool
def read_workspace_file(filename: str, thread_id: str = "default") -> dict[str, Any]:
    """Read the contents of a file in the thread's sandboxed workspace.

    Args:
        filename: Relative path or name of the file to read.
        thread_id: Unique thread identifier scoping the workspace.
    """
    try:
        path = _get_sandboxed_path(filename, thread_id)
        if not path.exists():
            return {"error": f"File '{filename}' does not exist in workspace.", "filename": filename}
        if not path.is_file():
            return {"error": f"'{filename}' is a directory, not a file.", "filename": filename}
        
        # Read with size cap (2MB)
        if path.stat().st_size > 2 * 1024 * 1024:
            return {"error": "File exceeds the 2MB read limit.", "filename": filename}

        content = path.read_text(encoding="utf-8", errors="replace")
        return {
            "filename": filename,
            "size_bytes": len(content),
            "content": content,
            "success": True,
        }
    except PermissionError as exc:
        return {"error": str(exc), "filename": filename, "success": False}
    except Exception as exc:
        return {"error": f"Failed to read file: {exc}", "filename": filename, "success": False}


@tool
def write_workspace_file(filename: str, content: str, thread_id: str = "default") -> dict[str, Any]:
    """Write text content to a file in the thread's sandboxed workspace.

    Args:
        filename: Relative path or name of the file to create or overwrite.
        content: Text content to write into the file.
        thread_id: Unique thread identifier scoping the workspace.
    """
    try:
        if len(content.encode("utf-8")) > 5 * 1024 * 1024:
            return {"error": "Content exceeds 5MB write limit.", "filename": filename, "success": False}

        path = _get_sandboxed_path(filename, thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "filename": filename,
            "size_bytes": path.stat().st_size,
            "success": True,
        }
    except PermissionError as exc:
        return {"error": str(exc), "filename": filename, "success": False}
    except Exception as exc:
        return {"error": f"Failed to write file: {exc}", "filename": filename, "success": False}


@tool
def list_workspace_files(thread_id: str = "default") -> dict[str, Any]:
    """List all files created in the thread's sandboxed workspace.

    Args:
        thread_id: Unique thread identifier scoping the workspace.
    """
    try:
        clean_tid = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(thread_id).strip()) or "default"
        thread_dir = (BASE_WORKSPACE_DIR / clean_tid).resolve()
        if not thread_dir.exists():
            return {"files": [], "total_files": 0, "thread_id": thread_id}

        files = []
        for p in thread_dir.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(thread_dir)).replace("\\", "/")
                files.append({
                    "name": rel,
                    "size_bytes": p.stat().st_size,
                    "modified": p.stat().st_mtime,
                })
        return {
            "files": files,
            "total_files": len(files),
            "thread_id": thread_id,
            "success": True,
        }
    except Exception as exc:
        return {"error": f"Failed to list workspace: {exc}", "success": False}


@tool
def delete_workspace_file(filename: str, thread_id: str = "default") -> dict[str, Any]:
    """Delete a file from the thread's sandboxed workspace.

    Args:
        filename: Relative path or name of the file to delete.
        thread_id: Unique thread identifier scoping the workspace.
    """
    try:
        path = _get_sandboxed_path(filename, thread_id)
        if not path.exists():
            return {"error": f"File '{filename}' does not exist.", "success": False}
        if not path.is_file():
            return {"error": f"'{filename}' is a directory and cannot be removed by this tool.", "success": False}
        path.unlink()
        return {"filename": filename, "deleted": True, "success": True}
    except PermissionError as exc:
        return {"error": str(exc), "filename": filename, "success": False}
    except Exception as exc:
        return {"error": f"Failed to delete file: {exc}", "filename": filename, "success": False}
