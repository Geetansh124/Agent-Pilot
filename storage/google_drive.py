"""Google Drive persistent storage backend.

Communicates with Google Drive API v3 via Service Account credentials for persistent
document, workspace, vector-store, export, and artifact storage across Render container lifecycles.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from storage.base import (
    ALLOWED_CATEGORIES,
    StorageBackend,
    guess_mime_type,
    resolve_category_and_thread,
    sanitize_relative_path,
    sanitize_thread_id,
)

logger = logging.getLogger("storage.google_drive")
SCOPES = ["https://www.googleapis.com/auth/drive"]


class GoogleDriveStorage(StorageBackend):
    """Google Drive storage backend implementing the StorageBackend interface."""

    def __init__(
        self,
        service_account_json: Optional[str | dict] = None,
        root_folder_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self._raw_creds = (
            service_account_json
            or kwargs.get("service_account_info")
            or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        )
        self._root_folder_id = (
            root_folder_id
            or kwargs.get("folder_id")
            or os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        )
        self._enabled = False
        self._service: Any = None
        self._folder_cache: dict[str, str] = {}  # "category/thread_id/subdirs" -> folder_id
        self._init_service()

    def _init_service(self) -> None:
        """Initialize Google Drive service client via User OAuth2 (refresh token) or Service Account."""
        # 1. Try User OAuth2 Credentials (bypasses Service Account 0-byte quota restrictions)
        oauth_json = os.getenv("GOOGLE_DRIVE_OAUTH_JSON")
        client_id = os.getenv("GOOGLE_DRIVE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET")
        refresh_token = os.getenv("GOOGLE_DRIVE_REFRESH_TOKEN")

        if oauth_json or (client_id and client_secret and refresh_token):
            try:
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                from googleapiclient.discovery import build

                if oauth_json:
                    info = self._parse_credentials_payload(oauth_json)
                    credentials = Credentials.from_authorized_user_info(info, scopes=SCOPES)
                else:
                    credentials = Credentials(
                        None,
                        refresh_token=refresh_token,
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=client_id,
                        client_secret=client_secret,
                        scopes=SCOPES,
                    )
                credentials.refresh(Request())
                self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
                self._enabled = True
                logger.info("Google Drive storage initialized successfully via User OAuth2 (personal quota active).")
                return
            except Exception as exc:
                logger.warning("Failed to initialize Google Drive via OAuth2: %s", exc)

        # 2. Try Service Account Credentials
        if not self._raw_creds:
            logger.info("Google Drive storage disabled: No OAuth2 or Service Account credentials provided.")
            self._enabled = False
            return

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds_data = self._parse_credentials_payload(self._raw_creds)
            credentials = service_account.Credentials.from_service_account_info(
                creds_data, scopes=SCOPES
            )
            self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
            self._enabled = True
            logger.info("Google Drive storage initialized successfully via Service Account.")
        except Exception as exc:
            # Never print secrets or full payload
            logger.warning("Failed to initialize Google Drive storage: %s", exc)
            self._enabled = False

    @staticmethod
    def _parse_credentials_payload(payload: str | dict) -> dict[str, Any]:
        """Parse service account JSON from dict, file path, raw JSON, or base64-encoded string."""
        if isinstance(payload, dict):
            return payload
        s = str(payload).strip()
        if os.path.isfile(s):
            with open(s, "r", encoding="utf-8") as fp:
                return json.load(fp)

        # Raw JSON string
        if s.startswith("{") and s.endswith("}"):
            return json.loads(s)

        # Base64-encoded JSON string
        try:
            decoded = base64.b64decode(s).decode("utf-8")
            if decoded.strip().startswith("{"):
                return json.loads(decoded)
        except Exception:
            pass

        raise ValueError("Invalid GOOGLE_SERVICE_ACCOUNT_JSON format. Expected file path, raw JSON, or base64 JSON.")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def backend_name(self) -> str:
        return "google_drive"

    def _escape_query_str(self, val: str) -> str:
        """Escape single quotes in Drive search queries."""
        return val.replace("'", "\\'")

    def _get_root_id(self) -> str:
        """Get or resolve root folder ID."""
        if self._root_folder_id:
            return self._root_folder_id
        if "root" in self._folder_cache:
            return self._folder_cache["root"]

        # Search for existing 'Agent-Pilot' folder in service account root
        escaped_name = self._escape_query_str("Agent-Pilot")
        q = f"'root' in parents and name = '{escaped_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = self._service.files().list(
            q=q,
            spaces="drive",
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = res.get("files", [])
        if files:
            folder_id = files[0]["id"]
        else:
            meta = {
                "name": "Agent-Pilot",
                "mimeType": "application/vnd.google-apps.folder",
                "parents": ["root"],
            }
            folder = self._service.files().create(
                body=meta,
                fields="id",
                supportsAllDrives=True,
            ).execute()
            folder_id = folder.get("id")

        self._folder_cache["root"] = folder_id
        return folder_id

    def get_or_create_folder(self, name: str, parent_id: str) -> str:
        """Find an existing folder under parent_id or create it idempotently."""
        cache_key = f"{parent_id}/{name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        escaped_name = self._escape_query_str(name)
        q = f"'{parent_id}' in parents and name = '{escaped_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = self._service.files().list(
            q=q,
            spaces="drive",
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = res.get("files", [])

        if files:
            folder_id = files[0]["id"]
        else:
            meta = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            folder = self._service.files().create(
                body=meta,
                fields="id",
                supportsAllDrives=True,
            ).execute()
            folder_id = folder.get("id")

        self._folder_cache[cache_key] = folder_id
        return folder_id

    def get_or_create_thread_folder(self, category: str, thread_id: str) -> str:
        """Get or create the specific category and thread folder path."""
        if category not in ALLOWED_CATEGORIES:
            raise ValueError(f"Category '{category}' is invalid. Allowed: {sorted(ALLOWED_CATEGORIES)}")

        clean_tid = sanitize_thread_id(thread_id)
        cache_key = f"{category}/{clean_tid}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        root_id = self._get_root_id()
        cat_folder_id = self.get_or_create_folder(category, root_id)
        thread_folder_id = self.get_or_create_folder(clean_tid, cat_folder_id)

        self._folder_cache[cache_key] = thread_folder_id
        return thread_folder_id

    def _resolve_target_folder(self, category: str, thread_id: str, relative_path: str) -> tuple[str, str]:
        """Resolve any nested subdirectories in relative_path and return (target_folder_id, leaf_filename)."""
        clean_rel = sanitize_relative_path(relative_path)
        parts = clean_rel.split("/")
        leaf_name = parts[-1]
        subdirs = parts[:-1]

        current_folder_id = self.get_or_create_thread_folder(category, thread_id)
        for sub in subdirs:
            current_folder_id = self.get_or_create_folder(sub, current_folder_id)

        return current_folder_id, leaf_name

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
        """Upload raw bytes into Google Drive with update-or-create semantics."""
        if not self._enabled:
            return {"error": "Google Drive storage disabled", "success": False}

        cat, tid = resolve_category_and_thread(category, thread_id, default_category="workspace")
        payload = file_bytes if file_bytes is not None else (data if data is not None else b"")
        folder_id, leaf_name = self._resolve_target_folder(cat or "workspace", tid, filename)
        mime = mime_type or guess_mime_type(leaf_name)

        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(io.BytesIO(payload), mimetype=mime, resumable=len(payload) > 5 * 1024 * 1024)

        # Search if file already exists in target folder to update in-place
        escaped_name = self._escape_query_str(leaf_name)
        q = f"'{folder_id}' in parents and name = '{escaped_name}' and trashed = false"
        res = self._service.files().list(
            q=q,
            spaces="drive",
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = res.get("files", [])

        if files:
            file_id = files[0]["id"]
            updated = self._service.files().update(
                fileId=file_id,
                media_body=media,
                fields="id, name, size, mimeType, modifiedTime",
                supportsAllDrives=True,
            ).execute()
            item = updated
        else:
            meta = {"name": leaf_name, "parents": [folder_id]}
            created = self._service.files().create(
                body=meta,
                media_body=media,
                fields="id, name, size, mimeType, modifiedTime",
                supportsAllDrives=True,
            ).execute()
            item = created

        return {
            "file_id": item.get("id"),
            "filename": filename,
            "name": leaf_name,
            "size_bytes": len(payload),
            "mime_type": mime,
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
        """Download raw file bytes from Google Drive."""
        if not self._enabled:
            return None

        try:
            cat, tid = resolve_category_and_thread(category, thread_id, default_category="workspace")
            file_meta = self.find_file(cat or "workspace", tid, filename)
            if not file_meta or not file_meta.get("id"):
                return None

            from googleapiclient.http import MediaIoBaseDownload

            file_id = file_meta["id"]
            request = self._service.files().get_media(fileId=file_id, supportsAllDrives=True)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return fh.getvalue()
        except Exception as exc:
            logger.warning("Failed to download '%s' from Google Drive: %s", filename, exc)
            return None

    def find_file(
        self,
        category: str,
        thread_id: str,
        filename: str,
    ) -> Optional[dict[str, Any]]:
        """Locate file metadata in Google Drive."""
        if not self._enabled:
            return None
        try:
            cat, tid = resolve_category_and_thread(category, thread_id, default_category="workspace")
            folder_id, leaf_name = self._resolve_target_folder(cat or "workspace", tid, filename)
            escaped = self._escape_query_str(leaf_name)
            q = f"'{folder_id}' in parents and name = '{escaped}' and trashed = false"
            res = self._service.files().list(
                q=q,
                spaces="drive",
                fields="files(id, name, mimeType, size, modifiedTime)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            files = res.get("files", [])
            return files[0] if files else None
        except Exception as exc:
            logger.warning("Failed to locate file '%s' in Google Drive: %s", filename, exc)
            return None

    def delete_file(
        self,
        category: Optional[str] = None,
        thread_id: Optional[str] = None,
        filename: str = "",
        **kwargs: Any,
    ) -> bool:
        """Delete file from Google Drive."""
        if not self._enabled:
            return False
        try:
            cat, tid = resolve_category_and_thread(category, thread_id, default_category="workspace")
            file_meta = self.find_file(cat or "workspace", tid, filename)
            if not file_meta or not file_meta.get("id"):
                return False
            self._service.files().delete(fileId=file_meta["id"], supportsAllDrives=True).execute()
            return True
        except Exception as exc:
            logger.warning("Failed to delete '%s' from Google Drive: %s", filename, exc)
            return False

    def list_files(
        self,
        *args: Any,
        category: Optional[str] = None,
        thread_id: Optional[str] = None,
        prefix: str = "",
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """List files in Google Drive folder."""
        if not self._enabled:
            return []
        try:
            cat, tid = resolve_category_and_thread(
                *args,
                category,
                thread_id,
                kwargs.get("category"),
                kwargs.get("thread_id"),
            )
            categories_to_scan = [cat] if cat else sorted(ALLOWED_CATEGORIES)
            output: list[dict[str, Any]] = []

            for current_cat in categories_to_scan:
                try:
                    folder_id = self.get_or_create_thread_folder(current_cat, tid)
                except Exception:
                    continue

                q = f"'{folder_id}' in parents and trashed = false"
                res = self._service.files().list(
                    q=q,
                    spaces="drive",
                    fields="files(id, name, mimeType, size, modifiedTime)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ).execute()
                files = res.get("files", [])

                for f in files:
                    if f.get("mimeType") == "application/vnd.google-apps.folder":
                        sub_q = f"'{f['id']}' in parents and trashed = false"
                        sub_res = self._service.files().list(
                            q=sub_q,
                            spaces="drive",
                            fields="files(id, name, mimeType, size, modifiedTime)",
                            supportsAllDrives=True,
                            includeItemsFromAllDrives=True,
                        ).execute()
                        for sf in sub_res.get("files", []):
                            if sf.get("mimeType") != "application/vnd.google-apps.folder":
                                rel_name = f"{f['name']}/{sf['name']}"
                                if not prefix or rel_name.startswith(prefix):
                                    output.append({
                                        "id": sf.get("id"),
                                        "name": rel_name,
                                        "size_bytes": int(sf.get("size", 0)),
                                        "mime_type": sf.get("mimeType"),
                                        "category": current_cat,
                                        "thread_id": tid,
                                        "modified": sf.get("modifiedTime"),
                                    })
                    else:
                        if not prefix or f["name"].startswith(prefix):
                            output.append({
                                "id": f.get("id"),
                                "name": f["name"],
                                "size_bytes": int(f.get("size", 0)),
                                "mime_type": f.get("mimeType"),
                                "category": current_cat,
                                "thread_id": tid,
                                "modified": f.get("modifiedTime"),
                            })
            return output
        except Exception as exc:
            logger.warning("Failed to list files from Google Drive: %s", exc)
            return []

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

    def health_check(self) -> bool:
        """Verify Google Drive API connectivity."""
        if not self._enabled or not self._service:
            return False
        try:
            root_id = self._root_folder_id or self._get_root_id()
            if root_id:
                res = self._service.files().get(
                    fileId=root_id,
                    fields="id, name, trashed",
                    supportsAllDrives=True,
                ).execute()
                return bool(res and res.get("id"))
            about = self._service.about().get(fields="user(emailAddress, displayName)").execute()
            return bool(about and "user" in about)
        except Exception as exc:
            logger.warning("Google Drive health check failed: %s", exc)
            return False

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
        if not self._enabled:
            return {"error": "Google Drive storage disabled", "success": False}

        clean_fn = Path(filename).name
        doc_folder_id = self.get_or_create_user_doc_folder(user_id, doc_id)
        mime = mime_type or guess_mime_type(clean_fn)

        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime, resumable=len(file_bytes) > 5 * 1024 * 1024)

        escaped_name = self._escape_query_str(clean_fn)
        q = f"'{doc_folder_id}' in parents and name = '{escaped_name}' and trashed = false"
        res = self._service.files().list(
            q=q,
            spaces="drive",
            fields="files(id, webViewLink)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = res.get("files", [])

        if files:
            file_id = files[0]["id"]
            updated = self._service.files().update(
                fileId=file_id,
                media_body=media,
                fields="id, name, size, mimeType, modifiedTime, webViewLink",
                supportsAllDrives=True,
            ).execute()
            item = updated
        else:
            meta = {"name": clean_fn, "parents": [doc_folder_id]}
            created = self._service.files().create(
                body=meta,
                media_body=media,
                fields="id, name, size, mimeType, modifiedTime, webViewLink",
                supportsAllDrives=True,
            ).execute()
            item = created

        meta_payload = {
            "doc_id": doc_id,
            "user_id": user_id,
            "filename": clean_fn,
            "size_bytes": len(file_bytes),
            "mime_type": mime,
            **(metadata or {}),
        }
        meta_media = MediaIoBaseUpload(
            io.BytesIO(json.dumps(meta_payload, indent=2).encode("utf-8")),
            mimetype="application/json",
        )
        self._service.files().create(
            body={"name": "metadata.json", "parents": [doc_folder_id]},
            media_body=meta_media,
            fields="id",
            supportsAllDrives=True,
        ).execute()

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

    def delete_user_document(
        self,
        user_id: str,
        doc_id: str,
        filename: Optional[str] = None,
    ) -> bool:
        if not self._enabled:
            return False
        try:
            doc_folder_id = self.get_or_create_user_doc_folder(user_id, doc_id)
            self._service.files().delete(fileId=doc_folder_id, supportsAllDrives=True).execute()
            cache_key = f"user_doc/{sanitize_thread_id(user_id)}/{sanitize_thread_id(doc_id)}"
            self._folder_cache.pop(cache_key, None)
            return True
        except Exception as exc:
            logger.warning("Failed to delete user document folder from Google Drive: %s", exc)
            return False

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
        """Persist FAISS index artifacts under Agent-Pilot/users/{user_id}/vectors/{doc_id}/."""
        if not self._enabled or vector_store is None:
            return False
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
            return False

    def load_user_vector_store(self, user_id: str, doc_id: str, embeddings: Any) -> Optional[Any]:
        """Download and reconstruct FAISS index from Agent-Pilot/users/{user_id}/vectors/{doc_id}/."""
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
                    file_id = files[0]["id"]
                    content = self._service.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
                    (Path(temp_dir) / fname).write_bytes(content)
                from langchain_community.vectorstores import FAISS
                return FAISS.load_local(temp_dir, embeddings, allow_dangerous_deserialization=True)
        except Exception as exc:
            logger.warning("Failed to load user vector store from Google Drive: %s", exc)
            return None

    def has_user_vector_store(self, user_id: str, doc_id: str) -> bool:
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
