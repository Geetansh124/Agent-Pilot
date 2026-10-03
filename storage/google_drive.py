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
import threading
import time
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
from storage.google_drive_tenant import GoogleDriveTenantMixin
from storage.google_drive_artifacts import GoogleDriveArtifactsMixin

logger = logging.getLogger("storage.google_drive")
SCOPES = ["https://www.googleapis.com/auth/drive"]


class GoogleDriveStorage(GoogleDriveTenantMixin, GoogleDriveArtifactsMixin, StorageBackend):
    """Google Drive storage backend implementing the StorageBackend interface."""

    _lock = threading.RLock()
    _last_health_check_time: float = 0.0
    _last_health_check_result: bool = False

    def __init__(self, service_account_json: Optional[str | dict] = None, root_folder_id: Optional[str] = None, **kwargs: Any) -> None:
        self._raw_creds = service_account_json or kwargs.get("service_account_info") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        self._root_folder_id = root_folder_id or kwargs.get("folder_id") or os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        self._enabled, self._service = False, None
        self._folder_cache: dict[str, str] = self._load_cache()
        self._init_service()

    def _load_cache(self) -> dict[str, str]:
        p = Path("workspaces_storage/.drive_cache.json")
        try:
            return json.loads(p.read_text("utf-8")) if p.exists() else {}
        except Exception:
            return {}

    def _save_cache(self) -> None:
        try:
            p = Path("workspaces_storage/.drive_cache.json")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._folder_cache), "utf-8")
        except Exception:
            pass

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
                import httplib2
                import google_auth_httplib2

                http = google_auth_httplib2.AuthorizedHttp(credentials, http=httplib2.Http(timeout=120.0))
                self._service = build("drive", "v3", http=http, cache_discovery=False)
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
            import httplib2
            import google_auth_httplib2

            creds_data = self._parse_credentials_payload(self._raw_creds)
            credentials = service_account.Credentials.from_service_account_info(
                creds_data, scopes=SCOPES
            )
            http = google_auth_httplib2.AuthorizedHttp(credentials, http=httplib2.Http(timeout=120.0))
            self._service = build("drive", "v3", http=http, cache_discovery=False)
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
        self._save_cache()
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
        folder_id = files[0]["id"] if files else self._service.files().create(
            body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
            fields="id",
            supportsAllDrives=True,
        ).execute().get("id")

        self._folder_cache[cache_key] = folder_id
        self._save_cache()
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
        self._save_cache()
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
            orderBy="modifiedTime desc",
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
            if len(files) > 1:
                for duplicate in files[1:]:
                    try:
                        self._service.files().delete(fileId=duplicate["id"], supportsAllDrives=True).execute()
                    except Exception:
                        pass
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
                orderBy="modifiedTime desc",
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

    def health_check(self, ttl: float = 60.0) -> bool:
        """Verify Google Drive API connectivity with TTL caching to avoid API rate limits."""
        if not self._enabled or not self._service:
            return False
        now = time.time()
        if (now - getattr(self, "_last_health_check_time", 0.0)) < ttl:
            return getattr(self, "_last_health_check_result", False)
        try:
            with self._lock:
                root_id = self._root_folder_id or self._get_root_id()
                if root_id:
                    res = self._service.files().get(fileId=root_id, fields="id, name, trashed", supportsAllDrives=True).execute()
                    res_ok = bool(res and res.get("id"))
                else:
                    about = self._service.about().get(fields="user(emailAddress, displayName)").execute()
                    res_ok = bool(about and "user" in about)
                self._last_health_check_time = now
                self._last_health_check_result = res_ok
                return res_ok
        except Exception as exc:
            logger.warning("Google Drive health check failed: %s", exc)
            self._last_health_check_time = now
            self._last_health_check_result = False
            return False
