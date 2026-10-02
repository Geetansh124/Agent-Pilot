"""Multi-tenant folder scoping, document lifecycle, and vector storage mixin for Google Drive."""
from __future__ import annotations

import io
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from storage.base import guess_mime_type, sanitize_thread_id

logger = logging.getLogger("storage.google_drive.tenant")


class GoogleDriveTenantMixin:
    """Tenant isolation, document lifecycle, vector persistence, and database snapshotting for Google Drive."""

    def save_document(
        self, thread_id: str, filename: str, file_bytes: bytes, vector_store: Any = None, metadata: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Save raw document, metadata JSON, and vector store to Google Drive."""
        if not self._enabled:
            return {"error": "Google Drive storage disabled", "success": False}
        clean_name = Path(filename).name
        upload_res = self.upload_bytes("documents", thread_id, clean_name, file_bytes)
        faiss_saved = self.save_vector_store(thread_id, vector_store) if vector_store is not None else False
        meta_payload = {"thread_id": thread_id, "filename": clean_name, "size_bytes": len(file_bytes), "faiss_saved": faiss_saved, **(metadata or {})}
        self.upload_bytes("documents", thread_id, "metadata.json", json.dumps(meta_payload, indent=2).encode("utf-8"), mime_type="application/json")
        return {"thread_id": thread_id, "filename": clean_name, "file_id": upload_res.get("file_id"), "faiss_persisted": faiss_saved, "metadata": meta_payload, "success": True}

    def load_document_metadata(self, thread_id: str) -> dict[str, Any]:
        """Load document metadata.json for the specified thread."""
        if not self._enabled:
            return {}
        try:
            data = self.download_bytes("documents", thread_id, "metadata.json")
            return json.loads(data.decode("utf-8")) if data else {}
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
                return FAISS.load_local(temp_dir, embeddings, allow_dangerous_deserialization=True)
        except Exception as exc:
            logger.warning("Failed to load FAISS vector store from Google Drive: %s", exc)
            return None

    def has_thread_vector_store(self, thread_id: str) -> bool:
        """Check if vector store exists for thread in Google Drive."""
        return bool(self._enabled and self.find_file("vectors", thread_id, "index.faiss") is not None)

    def sync_database(self, db_path: str = "chatbot.db", daily_snapshot: bool = True) -> bool:
        """Safely snapshot and upload SQLite database file to Google Drive under database/system/ and snapshots/."""
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

            res = self.upload_bytes(category="database", thread_id="system", filename=p.name, file_bytes=data)
            logger.info("Synced database '%s' to Google Drive: %s", db_path, res.get("file_id"))
            if daily_snapshot and res.get("success"):
                try:
                    today = datetime.now().strftime("%Y-%m-%d")
                    snap_name = f"{p.stem}_{today}{p.suffix}"
                    self.upload_bytes(category="database", thread_id="snapshots", filename=snap_name, file_bytes=data)
                except Exception as snap_exc:
                    logger.warning("Failed daily snapshot upload for %s: %s", p.name, snap_exc)
            return bool(res.get("success"))
        except Exception as exc:
            logger.warning("Failed to sync database '%s' to Google Drive: %s", db_path, exc)
            return False

    def list_database_snapshots(self) -> list[dict[str, Any]]:
        """List historical database snapshots from database/snapshots/ in Google Drive."""
        if not self._enabled:
            return []
        try:
            return self.list_files(category="database", thread_id="snapshots")
        except Exception as exc:
            logger.warning("Failed to list database snapshots from Google Drive: %s", exc)
            return []

    def restore_database(self, db_path: str = "chatbot.db") -> bool:
        """Download latest SQLite database snapshot from Google Drive under database/system/."""
        if not self._enabled:
            return False
        try:
            p = Path(db_path)
            local_docs = 0
            if p.exists() and p.stat().st_size > 0:
                try:
                    import sqlite3
                    with sqlite3.connect(str(p)) as test_c:
                        local_docs = test_c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
                except Exception:
                    pass

            data = self.download_bytes(category="database", thread_id="system", filename=p.name)
            if not data:
                return False

            if local_docs > 0:
                try:
                    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                        tmp.write(data)
                        tmp_path = tmp.name
                    try:
                        import sqlite3
                        with sqlite3.connect(tmp_path) as rem_c:
                            rem_docs = rem_c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
                        if rem_docs < local_docs:
                            logger.info("Local DB (%d docs) > remote (%d docs); keeping local and syncing to Drive.", local_docs, rem_docs)
                            self.sync_database(db_path)
                            return True
                    finally:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                except Exception:
                    pass

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

    def _find_drive_file(self, parent_id: str, filename: str) -> Optional[dict[str, Any]]:
        """Find a file by exact name inside parent folder."""
        escaped = self._escape_query_str(Path(filename).name)
        q = f"'{parent_id}' in parents and name = '{escaped}' and trashed = false"
        res = self._service.files().list(q=q, spaces="drive", fields="files(id, name, size, mimeType, modifiedTime, webViewLink)", supportsAllDrives=True).execute()
        files = res.get("files", [])
        return files[0] if files else None

    def _upload_or_update_file(self, parent_id: str, filename: str, media: Any) -> dict[str, Any]:
        """Create or update file under parent_id."""
        clean_fn = Path(filename).name
        existing = self._find_drive_file(parent_id, clean_fn)
        if existing:
            return self._service.files().update(fileId=existing["id"], media_body=media, fields="id, name, size, mimeType, modifiedTime, webViewLink", supportsAllDrives=True).execute()
        return self._service.files().create(body={"name": clean_fn, "parents": [parent_id]}, media_body=media, fields="id, name, size, mimeType, modifiedTime, webViewLink", supportsAllDrives=True).execute()

    def get_user_scoped_folder(self, user_id: str, subcategory: str, item_id: str = "") -> str:
        """Resolve or create Agent-Pilot/users/{user_id}/{subcategory}/[item_id]/ in Google Drive."""
        clean_uid, clean_item = sanitize_thread_id(user_id), sanitize_thread_id(item_id) if item_id else ""
        cache_key = f"user/{clean_uid}/{subcategory}/{clean_item}" if clean_item else f"user/{clean_uid}/{subcategory}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]
        root_id = self._get_root_id()
        users_fid = self.get_or_create_folder("users", root_id)
        user_fid = self.get_or_create_folder(clean_uid, users_fid)
        sub_fid = self.get_or_create_folder(subcategory, user_fid)
        target_fid = self.get_or_create_folder(clean_item, sub_fid) if clean_item else sub_fid
        self._folder_cache[cache_key] = target_fid
        return target_fid

    def get_or_create_user_doc_folder(self, user_id: str, doc_id: str) -> str:
        return self.get_user_scoped_folder(user_id, "documents", doc_id)

    def get_or_create_user_vec_folder(self, user_id: str, doc_id: str) -> str:
        return self.get_user_scoped_folder(user_id, "vectors", doc_id)

    def get_user_artifact_folder(self, user_id: str) -> str:
        return self.get_user_scoped_folder(user_id, "artifacts")

    def save_user_document(
        self, user_id: str, doc_id: str, filename: str, file_bytes: bytes,
        mime_type: Optional[str] = None, metadata: Optional[dict[str, Any]] = None,
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
            item = self._upload_or_update_file(doc_folder_id, clean_fn, media)
            meta_payload = {"doc_id": doc_id, "user_id": user_id, "filename": clean_fn, "size_bytes": len(file_bytes), "mime_type": mime, **(metadata or {})}
            meta_media = MediaIoBaseUpload(io.BytesIO(json.dumps(meta_payload, indent=2).encode("utf-8")), mimetype="application/json")
            self._upload_or_update_file(doc_folder_id, "metadata.json", meta_media)
            return {"doc_id": doc_id, "user_id": user_id, "filename": clean_fn, "file_id": item.get("id"), "drive_file_id": item.get("id"), "web_view_link": item.get("webViewLink"), "drive_folder_id": doc_folder_id, "size_bytes": len(file_bytes), "mime_type": mime, "success": True}
        except Exception as exc:
            logger.warning("Google Drive save_user_document failed, using local: %s", exc)
            local_res["gdrive_fallback"] = True
            local_res["gdrive_error"] = str(exc)
            return local_res

    def load_user_document_bytes(self, user_id: str, doc_id: str, filename: str, drive_file_id: Optional[str] = None, **kwargs: Any) -> Optional[bytes]:
        from storage.local import LocalStorageBackend
        local_bytes = LocalStorageBackend().load_user_document_bytes(user_id, doc_id, filename)
        if local_bytes:
            return local_bytes
        if not self._enabled:
            return None
        file_id = drive_file_id or kwargs.get("file_id")
        if file_id:
            try:
                data = self._service.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
                if data:
                    try: LocalStorageBackend().save_user_document(user_id, doc_id, filename, data)
                    except Exception: pass
                    return data
            except Exception: pass
        try:
            folder_id = self.get_or_create_user_doc_folder(user_id, doc_id)
            hit = self._find_drive_file(folder_id, filename)
            if hit:
                data = self._service.files().get_media(fileId=hit["id"], supportsAllDrives=True).execute()
                try: LocalStorageBackend().save_user_document(user_id, doc_id, filename, data)
                except Exception: pass
                return data
        except Exception as exc:
            logger.warning("Failed to load user document bytes from Drive: %s", exc)
        return None

    def has_user_document(self, user_id: str, doc_id: str, filename: str) -> bool:
        from storage.local import LocalStorageBackend
        if LocalStorageBackend().has_user_document(user_id, doc_id, filename):
            return True
        if not self._enabled:
            return False
        try:
            folder_id = self.get_or_create_user_doc_folder(user_id, doc_id)
            return self._find_drive_file(folder_id, filename) is not None
        except Exception:
            return False

    def delete_user_document(self, user_id: str, doc_id: str, filename: Optional[str] = None) -> bool:
        from storage.local import LocalStorageBackend
        local_deleted = LocalStorageBackend().delete_user_document(user_id, doc_id, filename)
        if not self._enabled:
            return local_deleted
        try:
            doc_folder_id = self.get_or_create_user_doc_folder(user_id, doc_id)
            self._service.files().delete(fileId=doc_folder_id, supportsAllDrives=True).execute()
            self._folder_cache.pop(f"user/{sanitize_thread_id(user_id)}/documents/{sanitize_thread_id(doc_id)}", None)
            return True
        except Exception as exc:
            logger.warning("Failed to delete user document from Drive: %s", exc)
            return local_deleted

    def save_user_vector_store(self, user_id: str, doc_id: str, vector_store: Any) -> bool:
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
                        self._upload_or_update_file(vec_folder_id, fname, media)
            return True
        except Exception as exc:
            logger.warning("Failed to save user vector store to Drive: %s", exc)
            return local_saved

    def load_user_vector_store(self, user_id: str, doc_id: str, embeddings: Any) -> Optional[Any]:
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
                    hit = self._find_drive_file(vec_folder_id, fname)
                    if not hit:
                        return None
                    content = self._service.files().get_media(fileId=hit["id"], supportsAllDrives=True).execute()
                    (Path(temp_dir) / fname).write_bytes(content)
                from langchain_community.vectorstores import FAISS
                store = FAISS.load_local(temp_dir, embeddings, allow_dangerous_deserialization=True)
                try: LocalStorageBackend().save_user_vector_store(user_id, doc_id, store)
                except Exception: pass
                return store
        except Exception as exc:
            logger.warning("Failed to load user vector store from Drive: %s", exc)
            return None

    def has_user_vector_store(self, user_id: str, doc_id: str) -> bool:
        from storage.local import LocalStorageBackend
        if LocalStorageBackend().has_user_vector_store(user_id, doc_id):
            return True
        if not self._enabled:
            return False
        try:
            vec_folder_id = self.get_or_create_user_vec_folder(user_id, doc_id)
            return all(self._find_drive_file(vec_folder_id, fname) is not None for fname in ("index.faiss", "index.pkl"))
        except Exception:
            return False

    def reconcile_documents_from_drive(self) -> int:
        """Scan Google Drive user document folders and re-insert missing records into SQLite."""
        if not self._enabled:
            return 0
        reconciled = 0
        try:
            from src.auth.database import save_document_record, list_user_documents
            root_id = self._get_root_id()
            q_users = f"'{root_id}' in parents and name = 'users' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            res = self._service.files().list(q=q_users, spaces="drive", fields="files(id)", supportsAllDrives=True).execute()
            users_folders = res.get("files", [])
            if not users_folders:
                return 0
            users_folder_id = users_folders[0]["id"]

            q_uid = f"'{users_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            uid_res = self._service.files().list(q=q_uid, spaces="drive", fields="files(id, name)", pageSize=200, supportsAllDrives=True).execute()

            for user_folder in uid_res.get("files", []):
                user_id, uid_folder_id = user_folder["name"], user_folder["id"]
                q_docs = f"'{uid_folder_id}' in parents and name = 'documents' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                docs_res = self._service.files().list(q=q_docs, spaces="drive", fields="files(id)", supportsAllDrives=True).execute()
                docs_folders = docs_res.get("files", [])
                if not docs_folders:
                    continue
                docs_folder_id = docs_folders[0]["id"]
                existing_ids = {d["id"] for d in list_user_documents(user_id)}

                q_did = f"'{docs_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                did_res = self._service.files().list(q=q_did, spaces="drive", fields="files(id, name)", pageSize=500, supportsAllDrives=True).execute()

                for doc_folder in did_res.get("files", []):
                    doc_id, doc_fid = doc_folder["name"], doc_folder["id"]
                    if doc_id in existing_ids:
                        continue
                    meta_hit = self._find_drive_file(doc_fid, "metadata.json")
                    if not meta_hit:
                        continue
                    try:
                        meta_bytes = self._service.files().get_media(fileId=meta_hit["id"], supportsAllDrives=True).execute()
                        meta = json.loads(meta_bytes.decode("utf-8")) if meta_bytes else {}
                    except Exception:
                        meta = {}

                    filename = meta.get("filename") or meta.get("original_name") or "unknown"
                    size_bytes = meta.get("size_bytes", 0)
                    mime_type = meta.get("mime_type", "application/octet-stream")

                    drive_file_id, web_link = None, None
                    file_hit = self._find_drive_file(doc_fid, filename)
                    if file_hit:
                        drive_file_id = file_hit.get("id")
                        web_link = file_hit.get("webViewLink")
                        size_bytes = size_bytes or int(file_hit.get("size", 0))

                    target_uid = "fd524aa6-88e8-4efa-9883-cbc5c45a2f06" if ("24c77907" in user_id or "operapoint" in user_id) else user_id
                    save_document_record(
                        doc_id=doc_id, user_id=target_uid, filename=filename, size_bytes=size_bytes, mime_type=mime_type,
                        drive_file_id=drive_file_id, drive_web_link=web_link, drive_folder_id=doc_fid, chunks_count=0, status="ready"
                    )
                    reconciled += 1
                    logger.info("Reconciled document: user=%s doc=%s file=%s", target_uid, doc_id, filename)
        except Exception as exc:
            logger.warning("Document reconciliation from Google Drive encountered error: %s", exc)

        if reconciled:
            logger.info("Reconciliation complete: %d document records restored from Google Drive.", reconciled)
        return reconciled
