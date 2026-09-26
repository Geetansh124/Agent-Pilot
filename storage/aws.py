"""AWS S3 and DynamoDB storage backend adapter.

Maintains backward-compatibility for AWS cloud persistence while conforming to StorageBackend.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from storage.base import (
    ALLOWED_CATEGORIES,
    StorageBackend,
    guess_mime_type,
    sanitize_relative_path,
    sanitize_thread_id,
)

logger = logging.getLogger("storage.aws")


class AWSStorageBackend(StorageBackend):
    """AWS S3 & DynamoDB storage backend implementing StorageBackend."""

    def __init__(self) -> None:
        self.bucket = os.getenv("AWS_S3_BUCKET")
        self.table_name = os.getenv("AWS_DYNAMODB_TABLE", "docupilot-documents")
        has_creds = bool(
            os.getenv("AWS_ACCESS_KEY_ID")
            or os.getenv("AWS_ROLE_ARN")
            or os.getenv("AWS_WEB_IDENTITY_TOKEN_FILE")
            or os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
        )
        self._enabled = bool(self.bucket and has_creds)
        self._s3: Any = None
        self._table: Any = None
        if self._enabled:
            try:
                import boto3

                endpoint_url = os.getenv("AWS_ENDPOINT_URL")
                session = boto3.session.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
                self._s3 = session.client("s3", endpoint_url=endpoint_url)
                if self.table_name:
                    try:
                        self._table = session.resource("dynamodb", endpoint_url=endpoint_url).Table(self.table_name)
                    except Exception:
                        self._table = None
            except Exception as exc:
                logger.warning("AWS client initialization failed: %s", exc)
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def backend_name(self) -> str:
        return "aws"

    def _get_key(self, category: str, thread_id: str, filename: str) -> str:
        clean_tid = sanitize_thread_id(thread_id)
        clean_fn = sanitize_relative_path(filename)
        return f"{category}/{clean_tid}/{clean_fn}"

    def upload_bytes(
        self,
        category: str,
        thread_id: str,
        filename: str,
        file_bytes: bytes,
        mime_type: Optional[str] = None,
    ) -> dict[str, Any]:
        """Upload raw bytes to S3."""
        if not self._enabled or not self._s3:
            return {"error": "AWS storage disabled", "success": False}

        key = self._get_key(category, thread_id, filename)
        mime = mime_type or guess_mime_type(filename)
        try:
            self._s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=file_bytes,
                ContentType=mime,
            )
            return {
                "file_id": key,
                "filename": filename,
                "size_bytes": len(file_bytes),
                "mime_type": mime,
                "category": category,
                "thread_id": thread_id,
                "success": True,
            }
        except Exception as exc:
            logger.warning("Failed S3 upload for '%s': %s", key, exc)
            return {"error": str(exc), "success": False}

    def download_bytes(
        self,
        category: str,
        thread_id: str,
        filename: str,
    ) -> Optional[bytes]:
        """Download raw bytes from S3."""
        if not self._enabled or not self._s3:
            return None
        key = self._get_key(category, thread_id, filename)
        try:
            resp = self._s3.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read()
        except Exception:
            return None

    def delete_file(
        self,
        category: str,
        thread_id: str,
        filename: str,
    ) -> bool:
        """Delete object from S3."""
        if not self._enabled or not self._s3:
            return False
        key = self._get_key(category, thread_id, filename)
        try:
            self._s3.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            logger.warning("Failed to delete S3 object '%s': %s", key, exc)
            return False

    def list_files(
        self,
        category: str,
        thread_id: str,
        prefix: str = "",
    ) -> list[dict[str, Any]]:
        """List files from S3 bucket under category/thread_id/."""
        if not self._enabled or not self._s3:
            return []

        clean_tid = sanitize_thread_id(thread_id)
        s3_prefix = f"{category}/{clean_tid}/"
        if prefix:
            s3_prefix += sanitize_relative_path(prefix)

        try:
            resp = self._s3.list_objects_v2(Bucket=self.bucket, Prefix=s3_prefix)
            results: list[dict[str, Any]] = []
            for item in resp.get("Contents", []):
                key = item.get("Key", "")
                rel_name = key[len(s3_prefix) :] if key.startswith(s3_prefix) else key
                results.append({
                    "id": key,
                    "name": rel_name,
                    "size_bytes": item.get("Size", 0),
                    "modified": str(item.get("LastModified", "")),
                    "mime_type": guess_mime_type(rel_name),
                })
            return results
        except Exception as exc:
            logger.warning("Failed to list S3 objects: %s", exc)
            return []

    def find_file(
        self,
        category: str,
        thread_id: str,
        filename: str,
    ) -> Optional[dict[str, Any]]:
        """Head object in S3."""
        if not self._enabled or not self._s3:
            return None
        key = self._get_key(category, thread_id, filename)
        try:
            resp = self._s3.head_object(Bucket=self.bucket, Key=key)
            return {
                "id": key,
                "name": Path(filename).name,
                "size": resp.get("ContentLength", 0),
                "mimeType": resp.get("ContentType", ""),
            }
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
        """Save uploaded document, metadata, and optional vector store."""
        upload_res = self.upload_bytes("documents", thread_id, filename, file_bytes)
        faiss_saved = False
        if vector_store is not None:
            faiss_saved = self.save_vector_store(thread_id, vector_store)

        meta_payload = {
            "thread_id": thread_id,
            "filename": filename,
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
        if self._table is not None:
            try:
                self._table.put_item(Item=meta_payload)
            except Exception as exc:
                logger.warning("DynamoDB save skipped: %s", exc)

        return {**upload_res, "metadata": meta_payload, "faiss_persisted": faiss_saved}

    def load_document_metadata(self, thread_id: str) -> dict[str, Any]:
        """Load document metadata from DynamoDB or S3."""
        if self._table is not None:
            try:
                resp = self._table.get_item(Key={"thread_id": thread_id})
                if "Item" in resp:
                    return resp["Item"]
            except Exception:
                pass

        data = self.download_bytes("documents", thread_id, "metadata.json")
        if data:
            try:
                return json.loads(data.decode("utf-8"))
            except Exception:
                pass
        return {}

    def save_vector_store(self, thread_id: str, vector_store: Any) -> bool:
        """Persist FAISS index artifacts to S3."""
        if not self._enabled or vector_store is None:
            return False
        try:
            with tempfile.TemporaryDirectory() as directory:
                vector_store.save_local(directory)
                for artifact in (Path(directory) / "index.faiss", Path(directory) / "index.pkl"):
                    if artifact.exists():
                        self.upload_bytes("vectors", thread_id, artifact.name, artifact.read_bytes())
            return True
        except Exception as exc:
            logger.warning("Failed to save vector store to S3: %s", exc)
            return False

    def load_vector_store(self, thread_id: str, embeddings: Any) -> Optional[Any]:
        """Download and load FAISS vector store from S3."""
        if not self._enabled:
            return None
        try:
            faiss_bytes = self.download_bytes("vectors", thread_id, "index.faiss")
            pkl_bytes = self.download_bytes("vectors", thread_id, "index.pkl")
            if not faiss_bytes or not pkl_bytes:
                return None

            with tempfile.TemporaryDirectory() as directory:
                (Path(directory) / "index.faiss").write_bytes(faiss_bytes)
                (Path(directory) / "index.pkl").write_bytes(pkl_bytes)
                from langchain_community.vectorstores import FAISS

                return FAISS.load_local(directory, embeddings, allow_dangerous_deserialization=True)
        except Exception as exc:
            logger.warning("Failed to load vector store from S3: %s", exc)
            return None

    def has_thread_vector_store(self, thread_id: str) -> bool:
        """Check if vector store exists in S3."""
        if not self._enabled:
            return False
        return self.find_file("vectors", thread_id, "index.faiss") is not None

    def health_check(self) -> bool:
        """Verify S3 connectivity."""
        if not self._enabled or not self._s3 or not self.bucket:
            return False
        try:
            self._s3.head_bucket(Bucket=self.bucket)
            return True
        except Exception as exc:
            logger.warning("AWS health check failed: %s", exc)
            return False
