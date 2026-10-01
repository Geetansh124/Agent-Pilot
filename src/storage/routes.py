"""Document storage and management routes for Agent-Pilot.

Provides /api/documents, /api/documents/upload, /api/threads/{thread_id}/document,
and document lifecycle operations scoped to authenticated users.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field

from src.auth.database import (
    attach_document_to_thread,
    delete_user_document_record,
    get_thread_active_document,
    get_user_document,
    list_user_documents,
    save_document_record,
)
from src.auth.middleware import get_current_user
from storage import storage

logger = logging.getLogger("storage.routes")
documents_router = APIRouter()

ALLOWED_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".doc", ".txt", ".md", ".markdown", ".csv", ".json", ".tsv"
})
MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_FILE_SIZE_MB", "500")) * 1024 * 1024  # 500 MB


class DocumentResponse(BaseModel):
    id: str
    user_id: str
    filename: str
    size_bytes: int
    mime_type: Optional[str] = None
    drive_file_id: Optional[str] = None
    drive_web_link: Optional[str] = None
    drive_folder_id: Optional[str] = None
    chunks_count: int = 0
    status: str = "ready"
    created_at: Optional[str] = None


class DocumentListResponse(BaseModel):
    documents: list[dict[str, Any]]
    total: int


def _extract_user_id(user: dict[str, Any]) -> str:
    """Safely extract tenant user id string from authenticated user payload."""
    sub = user.get("sub", "guest") if isinstance(user, dict) else "guest"
    if isinstance(sub, dict):
        return str(sub.get("sub") or sub.get("id") or "guest")
    return str(sub) if sub is not None else "guest"


@documents_router.get(
    "/documents",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all persistent documents belonging to current user",
)
def list_documents(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Retrieve all persistent documents for the authenticated user or guest."""
    user_id = _extract_user_id(user)
    docs = list_user_documents(user_id)
    return {"documents": docs, "total": len(docs)}


@documents_router.post(
    "/documents/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new document to persistent multi-tenant cloud storage",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    thread_id: Optional[str] = Form(None),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Upload document to Google Drive / local storage and register in database."""
    user_id = _extract_user_id(user)
    result = await _process_document_upload(file=file, user_id=user_id, thread_id=thread_id)
    # Sync SQLite to persistent storage so document records survive container restarts
    if hasattr(storage, "sync_database"):
        background_tasks.add_task(storage.sync_database, "chatbot.db")
    return result


@documents_router.post(
    "/threads/{thread_id}/document",
    status_code=status.HTTP_200_OK,
    summary="Upload document attached to an active thread (frontend compatible)",
)
async def upload_thread_document(
    thread_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Compatibility endpoint for thread-specific document attachments."""
    user_id = _extract_user_id(user)
    result = await _process_document_upload(file=file, user_id=user_id, thread_id=thread_id)
    if hasattr(storage, "sync_database"):
        background_tasks.add_task(storage.sync_database, "chatbot.db")
    return result


async def _process_document_upload(
    file: UploadFile,
    user_id: str,
    thread_id: Optional[str] = None,
) -> dict[str, Any]:
    """Validate, persist to storage adapter, record in database, and index for RAG."""
    filename = file.filename or "uploaded_document.pdf"
    lower_name = filename.lower()
    if not any(lower_name.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format for '{filename}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        err_status = getattr(status, "HTTP_413_CONTENT_TOO_LARGE", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        raise HTTPException(
            status_code=err_status,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB.",
        )

    doc_id = str(uuid.uuid4())

    # 1. Save into Storage Adapter (Google Drive / Local under users/{user_id}/documents/{doc_id}/)
    try:
        storage_res = storage.save_user_document(
            user_id=user_id,
            doc_id=doc_id,
            filename=filename,
            file_bytes=file_bytes,
            mime_type=file.content_type,
            metadata={"original_name": filename, "thread_id": thread_id},
        )
    except Exception as exc:
        logger.warning("Primary storage save failed (%s), attempting local fallback: %s", type(exc).__name__, exc)
        from storage.local import LocalStorageBackend
        try:
            storage_res = LocalStorageBackend().save_user_document(
                user_id=user_id,
                doc_id=doc_id,
                filename=filename,
                file_bytes=file_bytes,
                mime_type=file.content_type,
                metadata={"original_name": filename, "thread_id": thread_id},
            )
        except Exception as local_exc:
            logger.error("Both primary and fallback storage saves failed: %s", local_exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to persist file to storage backend: {exc}",
            ) from exc

    # 2. Extract, chunk, embed, and persist user-scoped vector store
    chunks_count = 0
    pages_count = 1
    vector_store = None
    chunks = None
    try:
        from src.tools.document_loader import load_document_from_bytes
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_community.vectorstores import FAISS
        from langraph_rag_backend import get_embeddings

        docs = load_document_from_bytes(file_bytes, filename)
        if docs:
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            chunks = splitter.split_documents(docs)
            for idx, chunk in enumerate(chunks):
                chunk.metadata["doc_id"] = doc_id
                chunk.metadata["filename"] = filename
                chunk.metadata["chunk_index"] = idx

            vector_store = FAISS.from_documents(chunks, get_embeddings())
            chunks_count = len(chunks)
            pages_count = len(docs)

            # Persist vector store in user-scoped partition
            storage.save_user_vector_store(user_id=user_id, doc_id=doc_id, vector_store=vector_store)
    except Exception as exc:
        logger.warning("User vector indexing warning for doc %s: %s", doc_id, exc)

    # 3. Save into Relational Database Table
    drive_file_id = storage_res.get("drive_file_id") or storage_res.get("file_id")
    web_view_link = storage_res.get("web_view_link")
    drive_folder_id = storage_res.get("drive_folder_id")

    record = save_document_record(
        doc_id=doc_id,
        user_id=user_id,
        filename=filename,
        size_bytes=len(file_bytes),
        mime_type=file.content_type or "application/octet-stream",
        drive_file_id=drive_file_id,
        drive_web_link=web_view_link,
        drive_folder_id=drive_folder_id,
        chunks_count=chunks_count,
        status="ready",
    )

    # 4. If thread_id is specified, attach to thread in DB and multi_doc_manager
    if thread_id:
        try:
            attach_document_to_thread(thread_id=thread_id, doc_id=doc_id, user_id=user_id)
            if vector_store:
                from src.rag import multi_doc_manager
                multi_doc_manager.attach_document(
                    thread_id=thread_id,
                    doc_id=doc_id,
                    filename=filename,
                    vector_store=vector_store,
                    chunks=chunks,
                )
        except Exception as exc:
            logger.warning("RAG thread attach warning for thread %s: %s", thread_id, exc)

    return {
        "id": doc_id,
        "doc_id": doc_id,
        "filename": filename,
        "size_bytes": len(file_bytes),
        "mime_type": record["mime_type"],
        "drive_file_id": drive_file_id,
        "web_view_link": web_view_link,
        "drive_folder_id": drive_folder_id,
        "chunks": chunks_count,
        "documents": pages_count,
        "status": "ready",
        "thread_id": thread_id,
    }


@documents_router.get(
    "/documents/{doc_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document details by ID",
)
def get_document(doc_id: str, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Retrieve document metadata ensuring strict user tenant scoping."""
    user_id = _extract_user_id(user)
    doc = get_user_document(doc_id, user_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found or access denied.",
        )
    return doc


@documents_router.delete(
    "/documents/{doc_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a persistent document from storage and database",
)
def delete_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete document from storage backend and relational database table."""
    user_id = _extract_user_id(user)
    doc = get_user_document(doc_id, user_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found or access denied.",
        )

    # Delete from storage backend
    try:
        storage.delete_user_document(user_id=user_id, doc_id=doc_id, filename=doc["filename"])
    except Exception as exc:
        logger.warning("Storage file deletion warning: %s", exc)

    # Delete database record
    delete_user_document_record(doc_id=doc_id, user_id=user_id)
    # Sync SQLite to persistent storage so deletions survive container restarts
    if hasattr(storage, "sync_database"):
        background_tasks.add_task(storage.sync_database, "chatbot.db")
    return {"message": "Document deleted successfully.", "doc_id": doc_id}


@documents_router.get(
    "/documents/{doc_id}/download",
    status_code=status.HTTP_200_OK,
    summary="Download original document file bytes",
)
def download_document(doc_id: str, user: dict[str, Any] = Depends(get_current_user)) -> Response:
    """Download raw document binary content with mime-type headers."""
    user_id = _extract_user_id(user)
    doc = get_user_document(doc_id, user_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found or access denied.",
        )

    raw_bytes = storage.load_user_document_bytes(user_id=user_id, doc_id=doc_id, filename=doc["filename"])
    if not raw_bytes:
        from storage.local import LocalStorageBackend
        raw_bytes = LocalStorageBackend().load_user_document_bytes(user_id=user_id, doc_id=doc_id, filename=doc["filename"])
    if not raw_bytes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file content not found in storage.")

    return Response(
        content=raw_bytes,
        media_type=doc.get("mime_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc["filename"]}"'},
    )


@documents_router.post(
    "/threads/{thread_id}/documents/{doc_id}/attach",
    status_code=status.HTTP_200_OK,
    summary="Attach any user-owned document to an active thread for grounded Q&A",
)
def attach_document_to_thread_endpoint(
    thread_id: str,
    doc_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Attach document to thread with on-demand cache warm-up and tenant isolation."""
    user_id = _extract_user_id(user)
    doc = get_user_document(doc_id, user_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found or access denied.",
        )

    # Attach in database
    attach_document_to_thread(thread_id=thread_id, doc_id=doc_id, user_id=user_id)

    # Warm up cache on demand: load or rebuild vector store
    from langraph_rag_backend import get_embeddings
    from src.rag import multi_doc_manager

    vector_store = None
    chunks = None
    if storage.has_user_vector_store(user_id=user_id, doc_id=doc_id):
        try:
            vector_store = storage.load_user_vector_store(
                user_id=user_id, doc_id=doc_id, embeddings=get_embeddings()
            )
        except Exception as exc:
            logger.warning("Failed loading persisted vector store for doc %s: %s", doc_id, exc)

    if vector_store is None:
        raw_bytes = storage.load_user_document_bytes(user_id=user_id, doc_id=doc_id, filename=doc["filename"])
        if raw_bytes:
            from langchain_community.vectorstores import FAISS
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            from src.tools.document_loader import load_document_from_bytes

            docs = load_document_from_bytes(raw_bytes, doc["filename"])
            if docs:
                splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
                chunks = splitter.split_documents(docs)
                for idx, chunk in enumerate(chunks):
                    chunk.metadata["doc_id"] = doc_id
                    chunk.metadata["filename"] = doc["filename"]
                    chunk.metadata["chunk_index"] = idx
                vector_store = FAISS.from_documents(chunks, get_embeddings())
                try:
                    storage.save_user_vector_store(user_id=user_id, doc_id=doc_id, vector_store=vector_store)
                except Exception as exc:
                    logger.warning("Failed re-persisting vector store: %s", exc)

    if vector_store:
        multi_doc_manager.attach_document(
            thread_id=thread_id,
            doc_id=doc_id,
            filename=doc["filename"],
            vector_store=vector_store,
            chunks=chunks,
        )

    return {
        "status": "attached",
        "thread_id": thread_id,
        "doc_id": doc_id,
        "filename": doc["filename"],
        "chunks_count": doc.get("chunks_count", 0),
    }


@documents_router.get(
    "/threads/{thread_id}/document",
    status_code=status.HTTP_200_OK,
    summary="Get currently active attached document for the thread",
)
def get_thread_active_document_endpoint(
    thread_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve active document metadata for this thread ensuring tenant isolation."""
    user_id = _extract_user_id(user)
    active_doc = get_thread_active_document(thread_id=thread_id, user_id=user_id)
    if not active_doc:
        return {"attached": False, "document": None}
    return {"attached": True, "document": active_doc}

