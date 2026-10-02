"""Google Drive mixin for artifacts, summaries, audit logs, and knowledge graph state."""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from storage.base import guess_mime_type

logger = logging.getLogger("storage.google_drive.artifacts")


class GoogleDriveArtifactsMixin:
    """Artifact, document summary, audit export, and knowledge graph mixin for Google Drive."""

    def get_user_artifact_folder(self, user_id: str) -> str:
        """Resolve or create Agent-Pilot/users/{user_id}/artifacts/ in Google Drive."""
        return self.get_user_scoped_folder(user_id, "artifacts")

    def save_document_summary(self, user_id: str, doc_id: str, summary_data: dict[str, Any]) -> bool:
        """Cache pre-computed document summary in local storage and Google Drive."""
        from storage.local import LocalStorageBackend
        LocalStorageBackend().save_document_summary(user_id, doc_id, summary_data)
        if not self._enabled:
            return True
        try:
            doc_folder_id = self.get_or_create_user_doc_folder(user_id, doc_id)
            from googleapiclient.http import MediaIoBaseUpload
            media = MediaIoBaseUpload(io.BytesIO(json.dumps(summary_data, indent=2).encode("utf-8")), mimetype="application/json")
            self._upload_or_update_file(doc_folder_id, "summary.json", media)
            return True
        except Exception as exc:
            logger.warning("Failed to save document summary to Drive: %s", exc)
            return False

    def load_document_summary(self, user_id: str, doc_id: str) -> Optional[dict[str, Any]]:
        """Load pre-computed document summary from local storage or Google Drive."""
        from storage.local import LocalStorageBackend
        cached = LocalStorageBackend().load_document_summary(user_id, doc_id)
        if cached is not None:
            return cached
        if not self._enabled:
            return None
        try:
            doc_folder_id = self.get_or_create_user_doc_folder(user_id, doc_id)
            hit = self._find_drive_file(doc_folder_id, "summary.json")
            if not hit:
                return None
            data = self._service.files().get_media(fileId=hit["id"], supportsAllDrives=True).execute()
            if data:
                parsed = json.loads(data.decode("utf-8"))
                try:
                    LocalStorageBackend().save_document_summary(user_id, doc_id, parsed)
                except Exception:
                    pass
                return parsed
        except Exception as exc:
            logger.warning("Failed to load document summary from Drive: %s", exc)
        return None

    def save_user_artifact(
        self,
        user_id: str,
        artifact_name: str,
        content: bytes | str,
        mime_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Save agent artifact (code, chart, export) to users/{user_id}/artifacts/."""
        raw = content.encode("utf-8") if isinstance(content, str) else content
        from storage.local import LocalStorageBackend
        local_res = LocalStorageBackend().save_user_artifact(user_id, artifact_name, raw, mime_type, metadata)
        if not self._enabled:
            return local_res
        try:
            art_folder_id = self.get_user_artifact_folder(user_id)
            clean_name = Path(artifact_name).name
            mime = mime_type or guess_mime_type(clean_name)
            from googleapiclient.http import MediaIoBaseUpload
            media = MediaIoBaseUpload(io.BytesIO(raw), mimetype=mime)
            item = self._upload_or_update_file(art_folder_id, clean_name, media)
            return {
                "user_id": user_id,
                "artifact_name": clean_name,
                "file_id": item.get("id"),
                "web_view_link": item.get("webViewLink"),
                "size_bytes": len(raw),
                "mime_type": mime,
                "metadata": metadata or {},
                "success": True,
            }
        except Exception as exc:
            logger.warning("Failed to save user artifact to Drive: %s", exc)
            return local_res

    def load_user_artifact(self, user_id: str, artifact_name: str) -> Optional[bytes]:
        """Load agent artifact bytes from local storage or Google Drive."""
        from storage.local import LocalStorageBackend
        local_bytes = LocalStorageBackend().load_user_artifact(user_id, artifact_name)
        if local_bytes is not None:
            return local_bytes
        if not self._enabled:
            return None
        try:
            art_folder_id = self.get_user_artifact_folder(user_id)
            hit = self._find_drive_file(art_folder_id, artifact_name)
            if not hit:
                return None
            data = self._service.files().get_media(fileId=hit["id"], supportsAllDrives=True).execute()
            if data:
                try:
                    LocalStorageBackend().save_user_artifact(user_id, artifact_name, data)
                except Exception:
                    pass
                return data
        except Exception as exc:
            logger.warning("Failed to load user artifact from Drive: %s", exc)
        return None

    def list_user_artifacts(self, user_id: str) -> list[dict[str, Any]]:
        """List all artifacts generated for the user."""
        from storage.local import LocalStorageBackend
        if not self._enabled:
            return LocalStorageBackend().list_user_artifacts(user_id)
        try:
            art_folder_id = self.get_user_artifact_folder(user_id)
            q = f"'{art_folder_id}' in parents and trashed = false"
            res = self._service.files().list(
                q=q, spaces="drive", fields="files(id, name, size, mimeType, modifiedTime, webViewLink)", supportsAllDrives=True
            ).execute()
            return [
                {
                    "name": f["name"],
                    "file_id": f["id"],
                    "size_bytes": int(f.get("size", 0)),
                    "mime_type": f.get("mimeType"),
                    "web_view_link": f.get("webViewLink"),
                    "modified": f.get("modifiedTime"),
                }
                for f in res.get("files", [])
            ]
        except Exception as exc:
            logger.warning("Failed to list user artifacts from Drive: %s", exc)
            return LocalStorageBackend().list_user_artifacts(user_id)

    def sync_audit_logs(self, db_path: str = "chatbot.db", limit: int = 500) -> bool:
        """Export latest audit log records to exports/audit/audit_export.json in Google Drive."""
        from storage.local import LocalStorageBackend
        LocalStorageBackend().sync_audit_logs(db_path, limit)
        if not self._enabled:
            return True
        try:
            import sqlite3
            p = Path(db_path)
            if not p.exists():
                return False
            with sqlite3.connect(str(p)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
                rows = [dict(r) for r in cursor.fetchall()]
            payload = json.dumps({"exported_at": datetime.now().isoformat(), "count": len(rows), "records": rows}, indent=2).encode("utf-8")
            res = self.upload_bytes("exports", "audit", "audit_export.json", payload, mime_type="application/json")
            return bool(res.get("success"))
        except Exception as exc:
            logger.warning("Failed to sync audit logs to Google Drive: %s", exc)
            return False

    def save_knowledge_graph(self, graph_data: dict[str, Any], scope: str = "system") -> bool:
        """Persist cross-document knowledge graph state to Google Drive."""
        from storage.local import LocalStorageBackend
        LocalStorageBackend().save_knowledge_graph(graph_data, scope)
        if not self._enabled:
            return True
        try:
            payload = json.dumps(graph_data, indent=2).encode("utf-8")
            res = self.upload_bytes("database", scope, "knowledge_graph.json", payload, mime_type="application/json")
            return bool(res.get("success"))
        except Exception as exc:
            logger.warning("Failed to save knowledge graph to Drive: %s", exc)
            return False

    def load_knowledge_graph(self, scope: str = "system") -> Optional[dict[str, Any]]:
        """Load cross-document knowledge graph state from Google Drive."""
        from storage.local import LocalStorageBackend
        cached = LocalStorageBackend().load_knowledge_graph(scope)
        if cached is not None:
            return cached
        if not self._enabled:
            return None
        try:
            data = self.download_bytes("database", scope, "knowledge_graph.json")
            if data:
                parsed = json.loads(data.decode("utf-8"))
                try:
                    LocalStorageBackend().save_knowledge_graph(parsed, scope)
                except Exception:
                    pass
                return parsed
        except Exception as exc:
            logger.warning("Failed to load knowledge graph from Drive: %s", exc)
        return None
