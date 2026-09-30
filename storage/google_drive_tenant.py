"""Multi-tenant folder scoping, document lifecycle, and vector storage mixin for Google Drive."""
from __future__ import annotations

import io
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from storage.base import guess_mime_type, sanitize_thread_id

logger = logging.getLogger("storage.google_drive.tenant")


class GoogleDriveTenantMixin:
    """Tenant isolation, document lifecycle, vector persistence, and database snapshotting for Google Drive."""

    def save_document(
        self,
        thread_id: str,
        filename: str,
        file_bytes: bytes,
        vector_store: Any = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Save raw document, metadata JSON, and vector store to Google Drive."""
        if not self._enabled:
            return {"error": "Google Drive storage disabled", "success": False}

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

        return {
            "thread_id": thread_id,
            "filename": clean_name,
            "file_id": upload_res.get("file_id"),
            "faiss_persisted": faiss_saved,
            "metadata": meta_payload,
            "success": True,
        }

    def load_document_metadata(self, thread_id: str) -> dict[str, Any]:
        """Load document metadata.json for the specified thread."""
        if not self._enabled:
            return {}
        try:
            data = self.download_bytes("documents", thread_id, "metadata.json")
            if not data:
                return {}
            return json.loads(data.decode("utf-8"))
        except Exception as exc:
            logger.warning("Failed to load document metadata from Google Drive: %s", exc)
            return {}

    def save_vector_store(self, thread_id: str, vector_store: Any) -> bool:
        """Persist FAISS index artifacts (index.faiss, index.pkl) to vectors/<thread_id>/ in Google Drive."""
        if not self._enabled or vector_store is None:
            return False

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                vector_store.save_local(temp_dir)
                for fname in ("index.faiss", "index.pkl"):
                    fpath = Path(temp_dir) / fname
                    if fpath.exists():
                        self.upload_bytes("vectors", thread_id, fname, fpath.read_bytes())
            logger.info("Successfully persisted FAISS index to Google Drive for thread %s", thread_id)
            return True
        except Exception as exc:
            logger.warning("Failed to save FAISS vector store to Google Drive: %s", exc)
            return False

    def load_vector_store(self, thread_id: str, embeddings: Any) -> Optional[Any]:
        """Download and reconstruct FAISS index from vectors/<thread_id>/ in Google Drive."""
        if not self._enabled:
            return None

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
            logger.warning("Failed to load FAISS vector store from Google Drive: %s", exc)
            return None

    def has_thread_vector_store(self, thread_id: str) -> bool:
        """Check if vector store exists for thread in Google Drive."""
        if not self._enabled:
            return False
        return self.find_file("vectors", thread_id, "index.faiss") is not None

    def sync_database(self, db_path: str = "chatbot.db") -> bool:
        """Safely snapshot and upload SQLite database file to Google Drive under database/system/."""
        if not self._enabled:
            return False
        p = Path(db_path)
        if not p.exists():
            return False
        try:
            import sqlite3
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                source = sqlite3.connect(str(p))
                dest = sqlite3.connect(tmp_path)
                source.backup(dest)
                source.close()
                dest.close()
                data = Path(tmp_path).read_bytes()
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

            res = self.upload_bytes(
                category="database",
                thread_id="system",
                filename=p.name,
                file_bytes=data,
            )
            logger.info("Synced database '%s' to Google Drive: %s", db_path, res.get("file_id"))
            return bool(res.get("success"))
        except Exception as exc:
            logger.warning("Failed to sync database '%s' to Google Drive: %s", db_path, exc)
            return False

    def restore_database(self, db_path: str = "chatbot.db") -> bool:
        """Download latest SQLite database snapshot from Google Drive under database/system/."""
        if not self._enabled:
            return False
        try:
            p = Path(db_path)
            data = self.download_bytes(category="database", thread_id="system", filename=p.name)
            if not data:
                return False
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            logger.info("Successfully restored database '%s' from Google Drive (%d bytes)", db_path, len(data))
            return True
        except Exception as exc:
            logger.warning("Failed to restore database '%s' from Google Drive: %s", db_path, exc)
            return False

    def sync_memory(self, memory_path: str = "memory.db") -> bool:
        """Sync long-term memory SQLite store to Google Drive."""
        return self.sync_database(memory_path)

    def restore_memory(self, memory_path: str = "memory.db") -> bool:
        """Restore long-term memory SQLite store from Google Drive."""
        return self.restore_database(memory_path)

    def get_or_create_user_doc_folder(self, user_id: str, doc_id: str) -> str:
        """Resolve or create Agent-Pilot/users/{user_id}/documents/{doc_id}/ folder in Google Drive."""
        clean_uid = sanitize_thread_id(user_id)
        clean_did = sanitize_thread_id(doc_id)
        cache_key = f"user_doc/{clean_uid}/{clean_did}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        root_id = self._get_root_id()
        users_folder_id = self.get_or_create_folder("users", root_id)
        user_folder_id = self.get_or_create_folder(clean_uid, users_folder_id)
        docs_folder_id = self.get_or_create_folder("documents", user_folder_id)
        doc_folder_id = self.get_or_create_folder(clean_did, docs_folder_id)

        self._folder_cache[cache_key] = doc_folder_id
        return doc_folder_id

    def save_user_document(
        self,
        user_id: str,
        doc_id: str,
        filename: str,
        file_bytes: bytes,
        mime_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Save a user-scoped document under Agent-Pilot/users/{user_id}/documents/{doc_id}/."""
        from storage.local import LocalStorageBackend
        local_res = LocalStorageBackend().save_user_document(user_id, doc_id, filename, file_bytes, mime_type, metadata)
        if not self._enabled:
            return local_res

        try:
            clean_fn = Path(filename).name
            doc_folder_id = self.get_or_create_user_doc_folder(user_id, doc_id)
            mime = mime_type or guess_mime_type(clean_fn)

            from googleapiclient.http import MediaIoBaseUpload
            media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime, resumable=len(file_bytes) > 5 * 1024 * 1024)

            escaped_name = self._escape_query_str(clean_fn)
            q = f"'{doc_folder_id}' in parents and name = '{escaped_name}' and trashed = false"
            res = self._service.files().list(
                q=q, spaces="drive", fields="files(id, webViewLink)", supportsAllDrives=True, includeItemsFromAllDrives=True
            ).execute()
            files = res.get("files", [])

            if files:
                item = self._service.files().update(
                    fileId=files[0]["id"], media_body=media, fields="id, name, size, mimeType, modifiedTime, webViewLink", supportsAllDrives=True
                ).execute()
            else:
                meta = {"name": clean_fn, "parents": [doc_folder_id]}
                item = self._service.files().create(
                    body=meta, media_body=media, fields="id, name, size, mimeType, modifiedTime, webViewLink", supportsAllDrives=True
                ).execute()

            meta_payload = {"doc_id": doc_id, "user_id": user_id, "filename": clean_fn, "size_bytes": len(file_bytes), "mime_type": mime, **(metadata or {})}
            meta_media = MediaIoBaseUpload(io.BytesIO(json.dumps(meta_payload, indent=2).encode("utf-8")), mimetype="application/json")
            self._service.files().create(body={"name": "metadata.json", "parents": [doc_folder_id]}, media_body=meta_media, fields="id", supportsAllDrives=True).execute()

            return {
                "doc_id": doc_id,
                "user_id": user_id,
                "filename": clean_fn,
                "file_id": item.get("id"),
                "drive_file_id": item.get("id"),
                "web_view_link": item.get("webViewLink"),
                "drive_folder_id": doc_folder_id,
                "size_bytes": len(file_bytes),
                "mime_type": mime,
                "success": True,
            }
        except Exception as exc:
            logger.warning("Google Drive save_user_document failed (%s), using local fallback: %s", type(exc).__name__, exc)
            local_res["gdrive_fallback"] = True
            local_res["gdrive_error"] = str(exc)
            return local_res

    def load_user_document_bytes(self, user_id: str, doc_id: str, filename: str) -> Optional[bytes]:
        """Download raw bytes of a user document with local cache check and Google Drive fallback."""
        from storage.local import LocalStorageBackend
        local_bytes = LocalStorageBackend().load_user_document_bytes(user_id, doc_id, filename)
        if local_bytes:
            return local_bytes

        if not self._enabled:
            return None
        try:
            folder_id = self.get_or_create_user_doc_folder(user_id, doc_id)
            escaped = self._escape_query_str(Path(filename).name)
            q = f"'{folder_id}' in parents and name = '{escaped}' and trashed = false"
            res = self._service.files().list(q=q, spaces="drive", fields="files(id)", supportsAllDrives=True).execute()
            files = res.get("files", [])
            if files:
                data = self._service.files().get_media(fileId=files[0]["id"], supportsAllDrives=True).execute()
                try:
                    LocalStorageBackend().save_user_document(user_id, doc_id, filename, data)
                except Exception:
                    pass
                return data
        except Exception as exc:
            logger.warning("Failed to load user document bytes from Google Drive: %s", exc)
        return None

    def has_user_document(self, user_id: str, doc_id: str, filename: str) -> bool:
        """Check whether user document exists in local cache or Google Drive."""
        from storage.local import LocalStorageBackend
        if LocalStorageBackend().has_user_document(user_id, doc_id, filename):
            return True
        if not self._enabled:
            return False
        try:
            folder_id = self.get_or_create_user_doc_folder(user_id, doc_id)
            escaped = self._escape_query_str(Path(filename).name)
            q = f"'{folder_id}' in parents and name = '{escaped}' and trashed = false"
            res = self._service.files().list(q=q, spaces="drive", fields="files(id)", supportsAllDrives=True).execute()
            return bool(res.get("files"))
        except Exception:
            return False

    def delete_user_document(self, user_id: str, doc_id: str, filename: Optional[str] = None) -> bool:
        """Delete user document from both local storage and Google Drive."""
        from storage.local import LocalStorageBackend
        local_deleted = LocalStorageBackend().delete_user_document(user_id, doc_id, filename)
        if not self._enabled:
            return local_deleted
        try:
            doc_folder_id = self.get_or_create_user_doc_folder(user_id, doc_id)
            self._service.files().delete(fileId=doc_folder_id, supportsAllDrives=True).execute()
            cache_key = f"user_doc/{sanitize_thread_id(user_id)}/{sanitize_thread_id(doc_id)}"
            self._folder_cache.pop(cache_key, None)
            return True
        except Exception as exc:
            logger.warning("Failed to delete user document folder from Google Drive: %s", exc)
            return local_deleted

    def get_or_create_user_vec_folder(self, user_id: str, doc_id: str) -> str:
        """Resolve or create Agent-Pilot/users/{user_id}/vectors/{doc_id}/ folder in Google Drive."""
        clean_uid = sanitize_thread_id(user_id)
        clean_did = sanitize_thread_id(doc_id)
        cache_key = f"user_vec/{clean_uid}/{clean_did}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        root_id = self._get_root_id()
        users_folder_id = self.get_or_create_folder("users", root_id)
        user_folder_id = self.get_or_create_folder(clean_uid, users_folder_id)
        vecs_folder_id = self.get_or_create_folder("vectors", user_folder_id)
        doc_vec_folder_id = self.get_or_create_folder(clean_did, vecs_folder_id)

        self._folder_cache[cache_key] = doc_vec_folder_id
        return doc_vec_folder_id

    def save_user_vector_store(self, user_id: str, doc_id: str, vector_store: Any) -> bool:
        """Persist FAISS index artifacts with local caching and Google Drive sync."""
        if vector_store is None:
            return False
        from storage.local import LocalStorageBackend
        local_saved = LocalStorageBackend().save_user_vector_store(user_id, doc_id, vector_store)
        if not self._enabled:
            return local_saved

        try:
            vec_folder_id = self.get_or_create_user_vec_folder(user_id, doc_id)
            with tempfile.TemporaryDirectory() as temp_dir:
                vector_store.save_local(temp_dir)
                for fname in ("index.faiss", "index.pkl"):
                    fpath = Path(temp_dir) / fname
                    if fpath.exists():
                        from googleapiclient.http import MediaIoBaseUpload
                        media = MediaIoBaseUpload(io.BytesIO(fpath.read_bytes()), mimetype="application/octet-stream")
                        escaped = self._escape_query_str(fname)
                        q = f"'{vec_folder_id}' in parents and name = '{escaped}' and trashed = false"
                        res = self._service.files().list(q=q, spaces="drive", fields="files(id)", supportsAllDrives=True).execute()
                        files = res.get("files", [])
                        if files:
                            self._service.files().update(fileId=files[0]["id"], media_body=media, supportsAllDrives=True).execute()
                        else:
                            self._service.files().create(body={"name": fname, "parents": [vec_folder_id]}, media_body=media, supportsAllDrives=True).execute()
            return True
        except Exception as exc:
            logger.warning("Failed to save user vector store to Google Drive: %s", exc)
            return local_saved

    def load_user_vector_store(self, user_id: str, doc_id: str, embeddings: Any) -> Optional[Any]:
        """Download and reconstruct FAISS index from local cache or Google Drive."""
        from storage.local import LocalStorageBackend
        local_store = LocalStorageBackend().load_user_vector_store(user_id, doc_id, embeddings)
        if local_store is not None:
            return local_store
        if not self._enabled:
            return None
        try:
            vec_folder_id = self.get_or_create_user_vec_folder(user_id, doc_id)
            with tempfile.TemporaryDirectory() as temp_dir:
                for fname in ("index.faiss", "index.pkl"):
                    escaped = self._escape_query_str(fname)
                    q = f"'{vec_folder_id}' in parents and name = '{escaped}' and trashed = false"
                    res = self._service.files().list(q=q, spaces="drive", fields="files(id)", supportsAllDrives=True).execute()
                    files = res.get("files", [])
                    if not files:
                        return None
                    content = self._service.files().get_media(fileId=files[0]["id"], supportsAllDrives=True).execute()
                    (Path(temp_dir) / fname).write_bytes(content)
                from langchain_community.vectorstores import FAISS
                store = FAISS.load_local(temp_dir, embeddings, allow_dangerous_deserialization=True)
                try:
                    LocalStorageBackend().save_user_vector_store(user_id, doc_id, store)
                except Exception:
                    pass
                return store
        except Exception as exc:
            logger.warning("Failed to load user vector store from Google Drive: %s", exc)
            return None

    def has_user_vector_store(self, user_id: str, doc_id: str) -> bool:
        """Check whether vector store exists in local cache or Google Drive."""
        from storage.local import LocalStorageBackend
        if LocalStorageBackend().has_user_vector_store(user_id, doc_id):
            return True
        if not self._enabled:
            return False
        try:
            vec_folder_id = self.get_or_create_user_vec_folder(user_id, doc_id)
            for fname in ("index.faiss", "index.pkl"):
                escaped = self._escape_query_str(fname)
                q = f"'{vec_folder_id}' in parents and name = '{escaped}' and trashed = false"
                res = self._service.files().list(q=q, spaces="drive", fields="files(id)", supportsAllDrives=True).execute()
                if not res.get("files"):
                    return False
            return True
        except Exception:
            return False
