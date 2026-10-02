"""Local filesystem storage backend for development, offline environments, and automated testing.

Provides identical interface and deterministic directory structure:
    workspaces_storage/
        documents/<thread_id>/
        workspace/<thread_id>/
        vectors/<thread_id>/
        exports/<thread_id>/
        attachments/<thread_id>/
        audio/<thread_id>/
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import tempfile
from typing import Any, Optional

from storage.base import (
    ALLOWED_CATEGORIES,
    StorageBackend,
    guess_mime_type,
    resolve_category_and_thread,
    sanitize_relative_path,
    sanitize_thread_id,
)

logger = logging.getLogger("storage.local")


class LocalStorageBackend(StorageBackend):
    """Local disk storage provider with strict sandbox scoping and thread isolation."""

    def __init__(self, base_dir: Optional[str | Path] = None):
        self.base_dir = Path(base_dir or "workspaces_storage").resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return True

    @property
    def backend_name(self) -> str:
        return "local"

    def _get_target_path(self, category: str, thread_id: str, relative_path: str = "") -> Path:
        """Resolve sandboxed directory and leaf path for a thread category."""
        if category not in ALLOWED_CATEGORIES:
            raise ValueError(f"Category '{category}' is invalid. Allowed: {sorted(ALLOWED_CATEGORIES)}")

        clean_tid = sanitize_thread_id(thread_id)
        category_dir = (self.base_dir / category / clean_tid).resolve()
        category_dir.mkdir(parents=True, exist_ok=True)

        if not relative_path:
            return category_dir

        clean_rel = sanitize_relative_path(relative_path)
        target = (category_dir / clean_rel).resolve()
        if not str(target).startswith(str(category_dir)):
            raise PermissionError(f"Access denied: path '{relative_path}' attempts directory traversal.")

        return target

    def upload_bytes(
        self,
        category: Optional[str] = None,
        thread_id: Optional[str] = None,
        filename: str = "",
        file_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
        data: Optional[bytes] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Write raw bytes to category/<thread_id>/<filename>."""
        cat, tid = resolve_category_and_thread(category, thread_id, default_category="workspace")
        payload = file_bytes if file_bytes is not None else (data if data is not None else b"")
        target = self._get_target_path(cat or "workspace", tid, filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

        return {
            "file_id": str(target),
            "filename": filename,
            "name": target.name,
            "size_bytes": len(payload),
            "mime_type": mime_type or guess_mime_type(target.name),
            "category": cat or "workspace",
            "thread_id": tid,
            "success": True,
        }

    def download_bytes(
        self,
        category: Optional[str] = None,
        thread_id: Optional[str] = None,
        filename: str = "",
        **kwargs: Any,
    ) -> Optional[bytes]:
        """Read raw bytes from category/<thread_id>/<filename>."""
        try:
            cat, tid = resolve_category_and_thread(category, thread_id, default_category="workspace")
            target = self._get_target_path(cat or "workspace", tid, filename)
            if not target.exists() or not target.is_file():
                return None
            return target.read_bytes()
        except Exception as exc:
            logger.warning("Local read failed for '%s': %s", filename, exc)
            return None

    def delete_file(
        self,
        category: Optional[str] = None,
        thread_id: Optional[str] = None,
        filename: str = "",
        **kwargs: Any,
    ) -> bool:
        """Delete file from category/<thread_id>/<filename>."""
        try:
            cat, tid = resolve_category_and_thread(category, thread_id, default_category="workspace")
            target = self._get_target_path(cat or "workspace", tid, filename)
            if target.exists() and target.is_file():
                target.unlink()
                return True
            return False
        except Exception as exc:
            logger.warning("Local delete failed for '%s': %s", filename, exc)
            return False

    def list_files(
        self,
        *args: Any,
        category: Optional[str] = None,
        thread_id: Optional[str] = None,
        prefix: str = "",
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """List files in category/<thread_id>/ or across all categories for thread."""
        try:
            cat, tid = resolve_category_and_thread(
                *args,
                category,
                thread_id,
                kwargs.get("category"),
                kwargs.get("thread_id"),
            )
            categories_to_scan = [cat] if cat else sorted(ALLOWED_CATEGORIES)
            files: list[dict[str, Any]] = []

            for current_cat in categories_to_scan:
                category_dir = self.base_dir / current_cat / tid
                if not category_dir.exists():
                    continue

                for p in category_dir.rglob("*"):
                    if p.is_file():
                        rel = str(p.relative_to(category_dir)).replace("\\", "/")
                        if not prefix or rel.startswith(prefix):
                            files.append({
                                "id": rel,
                                "name": rel,
                                "size_bytes": p.stat().st_size,
                                "mime_type": guess_mime_type(p.name),
                                "category": current_cat,
                                "thread_id": tid,
                                "modified": p.stat().st_mtime,
                            })
            return files
        except Exception as exc:
            logger.warning("Local list failed: %s", exc)
            return []

    def find_file(
        self,
        category: str,
        thread_id: str,
        filename: str,
    ) -> Optional[dict[str, Any]]:
        """Find file metadata."""
        try:
            cat, tid = resolve_category_and_thread(category, thread_id, default_category="workspace")
            target = self._get_target_path(cat or "workspace", tid, filename)
            if target.exists() and target.is_file():
                return {
                    "id": str(target),
                    "name": target.name,
                    "size": target.stat().st_size,
                    "mimeType": guess_mime_type(target.name),
                }
            return None
        except Exception:
            return None

    def save_document(
        self,
        thread_id: str,
        filename: str,
        file_bytes: bytes,
        vector_store: Any = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Save uploaded document, metadata JSON, and vector store."""
        clean_name = Path(filename).name
        upload_res = self.upload_bytes("documents", thread_id, clean_name, file_bytes)

        faiss_saved = False
        if vector_store is not None:
            faiss_saved = self.save_vector_store(thread_id, vector_store)

        meta_payload = {
            "thread_id": thread_id,
            "filename": clean_name,
            "size_bytes": len(file_bytes),
            "faiss_saved": faiss_saved,
            **(metadata or {}),
        }
        self.upload_bytes(
            "documents",
            thread_id,
            "metadata.json",
            json.dumps(meta_payload, indent=2).encode("utf-8"),
            mime_type="application/json",
        )
        return {**upload_res, "metadata": meta_payload, "faiss_persisted": faiss_saved}

    def load_document_metadata(self, thread_id: str) -> dict[str, Any]:
        """Load metadata.json for the specified thread."""
        data = self.download_bytes("documents", thread_id, "metadata.json")
        if not data:
            return {}
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            return {}

    def save_vector_store(self, thread_id: str, vector_store: Any) -> bool:
        """Persist FAISS index artifacts locally in vectors/<thread_id>/."""
        if vector_store is None:
            return False
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                vector_store.save_local(temp_dir)
                for fname in ("index.faiss", "index.pkl"):
                    p = Path(temp_dir) / fname
                    if p.exists():
                        self.upload_bytes("vectors", thread_id, fname, p.read_bytes())
            return True
        except Exception as exc:
            logger.warning("Local save vector store failed: %s", exc)
            return False

    def load_vector_store(self, thread_id: str, embeddings: Any) -> Optional[Any]:
        """Load FAISS index from vectors/<thread_id>/."""
        try:
            faiss_bytes = self.download_bytes("vectors", thread_id, "index.faiss")
            pkl_bytes = self.download_bytes("vectors", thread_id, "index.pkl")
            if not faiss_bytes or not pkl_bytes:
                return None

            with tempfile.TemporaryDirectory() as temp_dir:
                (Path(temp_dir) / "index.faiss").write_bytes(faiss_bytes)
                (Path(temp_dir) / "index.pkl").write_bytes(pkl_bytes)
                from langchain_community.vectorstores import FAISS

                store = FAISS.load_local(temp_dir, embeddings, allow_dangerous_deserialization=True)
                return store
        except Exception as exc:
            logger.warning("Local load vector store failed: %s", exc)
            return None

    def has_thread_vector_store(self, thread_id: str) -> bool:
        """Check if vector store exists for thread."""
        clean_tid = sanitize_thread_id(thread_id)
        vec_dir = self.base_dir / "vectors" / clean_tid
        return (vec_dir / "index.faiss").exists() and (vec_dir / "index.pkl").exists()

    def health_check(self) -> bool:
        """Local health check verifying directory write access."""
        test_file = self.base_dir / ".health_check"
        try:
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return True
        except Exception as exc:
            logger.warning("Local health check failed: %s", exc)
            return False

    def sync_database(self, db_path: str = "chatbot.db", daily_snapshot: bool = True) -> bool:
        """Backup local database file under database/system/ in storage and rolling daily snapshots."""
        p = Path(db_path)
        if not p.exists():
            return False
        try:
            data = p.read_bytes()
            res = self.upload_bytes("database", "system", p.name, data)
            if daily_snapshot and res.get("success"):
                from datetime import datetime
                snap_name = f"{p.stem}_{datetime.now().strftime('%Y-%m-%d')}{p.suffix}"
                self.upload_bytes("database", "snapshots", snap_name, data)
            return bool(res.get("success"))
        except Exception as exc:
            logger.warning("Local sync database failed: %s", exc)
            return False

    def list_database_snapshots(self) -> list[dict[str, Any]]:
        """List historical database snapshots from database/snapshots/."""
        return self.list_files(category="database", thread_id="snapshots")

    def restore_database(self, db_path: str = "chatbot.db") -> bool:
        """Restore local database file from database/system/ in storage."""
        try:
            p = Path(db_path)
            data = self.download_bytes("database", "system", p.name)
            if not data:
                return False
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            return True
        except Exception as exc:
            logger.warning("Local restore database failed: %s", exc)
            return False

    def sync_memory(self, memory_path: str = "memory.db") -> bool:
        return self.sync_database(memory_path)

    def restore_memory(self, memory_path: str = "memory.db") -> bool:
        return self.restore_database(memory_path)

    def _user_dir(self, user_id: str, subcat: str, item_id: str = "") -> Path:
        """Resolve sandboxed user subfolder workspaces_storage/users/{user_id}/{subcat}/[item_id]."""
        p = self.base_dir / "users" / sanitize_thread_id(user_id) / subcat
        if item_id:
            p = p / sanitize_thread_id(item_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_user_document(
        self, user_id: str, doc_id: str, filename: str, file_bytes: bytes,
        mime_type: Optional[str] = None, metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Save a user-scoped document in workspaces_storage/users/{user_id}/documents/{doc_id}/."""
        doc_dir = self._user_dir(user_id, "documents", doc_id)
        clean_fn = Path(filename).name
        target_file = doc_dir / clean_fn
        target_file.write_bytes(file_bytes)
        mime = mime_type or guess_mime_type(clean_fn)
        meta_payload = {"doc_id": doc_id, "user_id": user_id, "filename": clean_fn, "size_bytes": len(file_bytes), "mime_type": mime, **(metadata or {})}
        (doc_dir / "metadata.json").write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")
        return {"doc_id": doc_id, "user_id": user_id, "filename": clean_fn, "file_id": str(target_file), "drive_file_id": str(target_file), "drive_folder_id": str(doc_dir), "size_bytes": len(file_bytes), "mime_type": mime, "success": True}

    def load_user_document_bytes(self, user_id: str, doc_id: str, filename: str, **kwargs: Any) -> Optional[bytes]:
        target = self._user_dir(user_id, "documents", doc_id) / Path(filename).name
        return target.read_bytes() if target.exists() else None

    def has_user_document(self, user_id: str, doc_id: str, filename: str) -> bool:
        target = self._user_dir(user_id, "documents", doc_id) / Path(filename).name
        return target.exists() and target.is_file()

    def delete_user_document(self, user_id: str, doc_id: str, filename: Optional[str] = None) -> bool:
        doc_dir = self._user_dir(user_id, "documents", doc_id)
        if not doc_dir.exists():
            return True
        try:
            import shutil
            shutil.rmtree(doc_dir, ignore_errors=True)
            return True
        except Exception as exc:
            logger.warning("Failed to delete user document directory: %s", exc)
            return False

    def save_user_vector_store(self, user_id: str, doc_id: str, vector_store: Any) -> bool:
        if vector_store is None:
            return False
        vec_dir = self._user_dir(user_id, "vectors", doc_id)
        try:
            vector_store.save_local(str(vec_dir))
            return True
        except Exception as exc:
            logger.warning("Local save user vector store failed: %s", exc)
            return False

    def load_user_vector_store(self, user_id: str, doc_id: str, embeddings: Any) -> Optional[Any]:
        vec_dir = self._user_dir(user_id, "vectors", doc_id)
        if not ((vec_dir / "index.faiss").exists() and (vec_dir / "index.pkl").exists()):
            return None
        try:
            from langchain_community.vectorstores import FAISS
            return FAISS.load_local(str(vec_dir), embeddings, allow_dangerous_deserialization=True)
        except Exception as exc:
            logger.warning("Local load user vector store failed: %s", exc)
            return None

    def has_user_vector_store(self, user_id: str, doc_id: str) -> bool:
        vec_dir = self._user_dir(user_id, "vectors", doc_id)
        return (vec_dir / "index.faiss").exists() and (vec_dir / "index.pkl").exists()

    def save_document_summary(self, user_id: str, doc_id: str, summary_data: dict[str, Any]) -> bool:
        """Cache pre-computed document summary locally."""
        try:
            doc_dir = self._user_dir(user_id, "documents", doc_id)
            (doc_dir / "summary.json").write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
            return True
        except Exception as exc:
            logger.warning("Local save document summary failed: %s", exc)
            return False

    def load_document_summary(self, user_id: str, doc_id: str) -> Optional[dict[str, Any]]:
        """Load pre-computed document summary from local storage."""
        target = self._user_dir(user_id, "documents", doc_id) / "summary.json"
        if not target.exists():
            return None
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_user_artifact(
        self, user_id: str, artifact_name: str, content: bytes | str,
        mime_type: Optional[str] = None, metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Save agent-generated code/report/chart artifact to users/{user_id}/artifacts/."""
        art_dir = self._user_dir(user_id, "artifacts")
        clean_fn = Path(artifact_name).name
        target = art_dir / clean_fn
        raw = content.encode("utf-8") if isinstance(content, str) else content
        target.write_bytes(raw)
        mime = mime_type or guess_mime_type(clean_fn)
        return {"user_id": user_id, "artifact_name": clean_fn, "file_id": str(target), "size_bytes": len(raw), "mime_type": mime, "metadata": metadata or {}, "success": True}

    def load_user_artifact(self, user_id: str, artifact_name: str) -> Optional[bytes]:
        """Load agent artifact bytes from local storage."""
        target = self._user_dir(user_id, "artifacts") / Path(artifact_name).name
        return target.read_bytes() if target.exists() else None

    def list_user_artifacts(self, user_id: str) -> list[dict[str, Any]]:
        """List all artifacts generated for the user."""
        art_dir = self._user_dir(user_id, "artifacts")
        results = []
        for p in art_dir.iterdir():
            if p.is_file():
                results.append({"name": p.name, "file_id": str(p), "size_bytes": p.stat().st_size, "mime_type": guess_mime_type(p.name), "modified": p.stat().st_mtime})
        return results

    def sync_audit_logs(self, db_path: str = "chatbot.db", limit: int = 500) -> bool:
        """Export latest audit log records from SQLite to exports/audit/audit_export.json."""
        p = Path(db_path)
        if not p.exists():
            return False
        try:
            import sqlite3
            with sqlite3.connect(str(p)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
                rows = [dict(r) for r in cursor.fetchall()]
            from datetime import datetime
            payload = json.dumps({"exported_at": datetime.now().isoformat(), "count": len(rows), "records": rows}, indent=2).encode("utf-8")
            res = self.upload_bytes("exports", "audit", "audit_export.json", payload, mime_type="application/json")
            return bool(res.get("success"))
        except Exception as exc:
            logger.warning("Local sync audit logs failed: %s", exc)
            return False

    def save_knowledge_graph(self, graph_data: dict[str, Any], scope: str = "system") -> bool:
        """Persist cross-document knowledge graph state."""
        try:
            payload = json.dumps(graph_data, indent=2).encode("utf-8")
            res = self.upload_bytes("database", scope, "knowledge_graph.json", payload, mime_type="application/json")
            return bool(res.get("success"))
        except Exception as exc:
            logger.warning("Local save knowledge graph failed: %s", exc)
            return False

    def load_knowledge_graph(self, scope: str = "system") -> Optional[dict[str, Any]]:
        """Load cross-document knowledge graph state."""
        try:
            data = self.download_bytes("database", scope, "knowledge_graph.json")
            return json.loads(data.decode("utf-8")) if data else None
        except Exception as exc:
            logger.warning("Local load knowledge graph failed: %s", exc)
            return None

