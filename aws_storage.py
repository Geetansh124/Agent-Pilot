from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("aws_storage")


class AWSStorage:
    """Optional S3/DynamoDB persistence used when AWS credentials and bucket are configured."""

    def __init__(self) -> None:
        self.bucket = os.getenv("AWS_S3_BUCKET")
        self.table_name = os.getenv("AWS_DYNAMODB_TABLE", "docupilot-documents")
        has_creds = bool(
            os.getenv("AWS_ACCESS_KEY_ID")
            or os.getenv("AWS_ROLE_ARN")
            or os.getenv("AWS_WEB_IDENTITY_TOKEN_FILE")
            or os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
        )
        self.enabled = bool(self.bucket and has_creds)
        self._s3 = None
        self._table = None
        if self.enabled:
            try:
                import boto3
                session = boto3.session.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
                self._s3 = session.client("s3")
                self._table = session.resource("dynamodb").Table(self.table_name)
            except Exception as exc:
                logger.warning("AWS client initialization failed, falling back to in-memory: %s", exc)
                self.enabled = False

    def save_document(self, thread_id: str, filename: str, file_bytes: bytes, vector_store: Any, metadata: dict) -> None:
        if not self.enabled:
            return
        try:
            assert self._s3 is not None and self._table is not None
            safe_name = Path(filename).name
            safe_thread_id = re.sub(r"[^A-Za-z0-9._-]", "_", thread_id)
            prefix = f"threads/{safe_thread_id}"
            self._s3.put_object(Bucket=self.bucket, Key=f"{prefix}/documents/{safe_name}", Body=file_bytes, ContentType="application/pdf")
            with tempfile.TemporaryDirectory() as directory:
                vector_store.save_local(directory)
                for artifact in (Path(directory) / "index.faiss", Path(directory) / "index.pkl"):
                    self._s3.upload_file(str(artifact), self.bucket, f"{prefix}/faiss/{artifact.name}")
            item = {"thread_id": thread_id, **metadata, "s3_prefix": prefix}
            self._table.put_item(Item=item)
        except Exception as exc:
            logger.warning("Failed to persist document to AWS S3/DynamoDB: %s", exc)

    def load_document_metadata(self, thread_id: str) -> dict:
        if not self.enabled:
            return {}
        try:
            assert self._table is not None
            response = self._table.get_item(Key={"thread_id": thread_id})
            return response.get("Item", {})
        except Exception as exc:
            logger.warning("Failed to load document metadata from AWS: %s", exc)
            return {}

    def load_vector_store(self, thread_id: str, embeddings: Any) -> Any | None:
        if not self.enabled:
            return None
        try:
            assert self._s3 is not None
            safe_thread_id = re.sub(r"[^A-Za-z0-9._-]", "_", thread_id)
            prefix = f"threads/{safe_thread_id}/faiss"
            with tempfile.TemporaryDirectory() as directory:
                for name in ("index.faiss", "index.pkl"):
                    try:
                        self._s3.download_file(
                            self.bucket,
                            f"{prefix}/{name}",
                            str(Path(directory) / name),
                        )
                    except self._s3.exceptions.NoSuchKey:
                        return None
                from langchain_community.vectorstores import FAISS
                return FAISS.load_local(directory, embeddings, allow_dangerous_deserialization=True)
        except Exception as exc:
            logger.warning("Failed to load vector store from AWS: %s", exc)
            return None


storage = AWSStorage()
