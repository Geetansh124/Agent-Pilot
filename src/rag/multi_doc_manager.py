"""Multi-document manager for per-thread RAG.

Maintains multi-document vector indexes, document provenance tracking,
and incremental merging of FAISS vector stores per conversation thread.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.rag.hybrid_retriever import HybridRetriever
from src.tools.document_loader import load_document_from_bytes


class MultiDocManager:
    """Manages multi-document index collections for chat threads."""

    def __init__(self):
        self._thread_stores: dict[str, FAISS] = {}
        self._thread_docs: dict[str, list[dict[str, Any]]] = {}
        self._thread_chunks: dict[str, list[Document]] = {}
        self._thread_retrievers: dict[str, HybridRetriever] = {}

    def has_documents(self, thread_id: str) -> bool:
        """Check if any document is indexed for the thread."""
        return bool(self._thread_docs.get(str(thread_id)))

    def get_documents(self, thread_id: str) -> list[dict[str, Any]]:
        """Return metadata for all documents registered for the thread."""
        return list(self._thread_docs.get(str(thread_id), []))

    def get_vector_store(self, thread_id: str) -> Optional[FAISS]:
        """Return the active FAISS vector store for the thread."""
        return self._thread_stores.get(str(thread_id))

    def register_vector_store(
        self,
        thread_id: str,
        store: FAISS,
        docs: Optional[list[dict[str, Any]]] = None,
        chunks: Optional[list[Document]] = None,
    ) -> None:
        """Register or restore an existing FAISS vector store into the thread's cache."""
        tid = str(thread_id)
        self._thread_stores[tid] = store
        if chunks is not None:
            self._thread_chunks[tid] = list(chunks)
        elif tid not in self._thread_chunks:
            self._thread_chunks[tid] = []

        if docs is not None:
            self._thread_docs[tid] = list(docs)
        elif tid not in self._thread_docs:
            self._thread_docs[tid] = [{"doc_id": "restored", "filename": "restored_store"}]

        # Create or update hybrid retriever
        self._thread_retrievers[tid] = HybridRetriever(
            vector_store=store,
            all_documents=self._thread_chunks[tid],
        )

    def get_hybrid_retriever(self, thread_id: str) -> Optional[HybridRetriever]:
        """Return the active hybrid retriever for the thread."""
        tid = str(thread_id)
        return self._thread_retrievers.get(tid)

    def get_or_restore_retriever(
        self,
        thread_id: str,
        embeddings: Any,
        storage_backend: Any = None,
    ) -> Optional[HybridRetriever]:
        """Fetch active hybrid retriever or restore on demand from persisted vector store."""
        tid = str(thread_id)
        if tid in self._thread_retrievers:
            return self._thread_retrievers[tid]

        # 1. Attempt restoration from user-scoped attached document in database
        try:
            from src.auth.database import get_thread_active_document
            active_doc = get_thread_active_document(tid)
            if active_doc and storage_backend:
                uid = active_doc["user_id"]
                did = active_doc["doc_id"]
                store = None
                chunks = None
                if hasattr(storage_backend, "has_user_vector_store") and storage_backend.has_user_vector_store(uid, did):
                    try:
                        store = storage_backend.load_user_vector_store(uid, did, embeddings)
                    except Exception:
                        store = None

                # On-demand fallback: rebuild vector store from persistent document bytes if not yet indexed
                if store is None and hasattr(storage_backend, "load_user_document_bytes"):
                    try:
                        raw_bytes = storage_backend.load_user_document_bytes(
                            user_id=uid,
                            doc_id=did,
                            filename=active_doc["filename"],
                            drive_file_id=active_doc.get("drive_file_id"),
                        )
                        if raw_bytes:
                            docs = load_document_from_bytes(raw_bytes, active_doc["filename"])
                            if docs:
                                splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
                                all_chunks = splitter.split_documents(docs)
                                chunks = all_chunks[:40]
                                for idx, chunk in enumerate(chunks):
                                    chunk.metadata["doc_id"] = did
                                    chunk.metadata["filename"] = active_doc["filename"]
                                    chunk.metadata["chunk_index"] = idx
                                store = FAISS.from_documents(chunks, embeddings)
                                if hasattr(storage_backend, "save_user_vector_store"):
                                    storage_backend.save_user_vector_store(uid, did, store)
                                try:
                                    from src.auth.database import get_db_connection
                                    with get_db_connection() as conn:
                                        conn.cursor().execute(
                                            "UPDATE documents SET chunks_count = ? WHERE id = ?",
                                            (len(chunks), did),
                                        )
                                        conn.commit()
                                except Exception:
                                    pass
                    except Exception:
                        pass

                if store:
                    self.attach_document(tid, did, active_doc["filename"], store, chunks=chunks)
                    return self._thread_retrievers.get(tid)
        except Exception:
            pass

        # 2. Fallback: thread-level vector store
        if storage_backend and getattr(storage_backend, "enabled", False) and hasattr(storage_backend, "load_vector_store"):
            store = storage_backend.load_vector_store(tid, embeddings)
            if store is not None:
                self.register_vector_store(tid, store)
                return self._thread_retrievers.get(tid)

        return None

    def attach_document(
        self,
        thread_id: str,
        doc_id: str,
        filename: str,
        vector_store: FAISS,
        chunks: Optional[list[Document]] = None,
    ) -> dict[str, Any]:
        """Attach a persistent document's vector store to an active thread for grounded Q&A."""
        tid = str(thread_id)
        doc_summary = {
            "doc_id": doc_id,
            "filename": filename,
            "chunks": len(chunks) if chunks else 1,
            "total_thread_docs": len(self._thread_docs.get(tid, [])) + 1,
        }
        self.register_vector_store(
            thread_id=tid,
            store=vector_store,
            docs=[doc_summary],
            chunks=chunks,
        )
        return doc_summary

    def ingest_document(
        self,
        file_bytes: bytes,
        thread_id: str,
        filename: str,
        embeddings: Any,
    ) -> dict[str, Any]:
        """Ingest a new document (PDF, DOCX, CSV, TXT, MD) and merge into the thread's index."""
        if not file_bytes:
            raise ValueError("No file bytes provided for ingestion.")

        tid = str(thread_id)
        doc_id = str(uuid.uuid4())[:8]
        docs = load_document_from_bytes(file_bytes, filename)
        if not docs:
            raise ValueError(f"Unable to extract text from '{filename}'.")

        # Split into chunks and stamp chunk metadata with document provenance
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200, separators=["\n\n", "\n", " ", ""]
        )
        chunks = splitter.split_documents(docs)
        for idx, chunk in enumerate(chunks):
            chunk.metadata["doc_id"] = doc_id
            chunk.metadata["filename"] = filename
            chunk.metadata["chunk_index"] = idx

        # Incremental FAISS merge
        new_store = FAISS.from_documents(chunks, embeddings)
        if tid in self._thread_stores:
            self._thread_stores[tid].merge_from(new_store)
            self._thread_chunks[tid].extend(chunks)
        else:
            self._thread_stores[tid] = new_store
            self._thread_chunks[tid] = list(chunks)

        # Update hybrid retriever
        self._thread_retrievers[tid] = HybridRetriever(
            vector_store=self._thread_stores[tid],
            all_documents=self._thread_chunks[tid],
        )

        doc_summary = {
            "doc_id": doc_id,
            "filename": filename,
            "documents": len(docs),
            "chunks": len(chunks),
            "total_thread_docs": len(self._thread_docs.get(tid, [])) + 1,
        }

        if tid not in self._thread_docs:
            self._thread_docs[tid] = []
        self._thread_docs[tid].append(doc_summary)

        return doc_summary

    def remove_thread(self, thread_id: str) -> None:
        """Clear all in-memory indexes and metadata for a thread."""
        tid = str(thread_id)
        self._thread_stores.pop(tid, None)
        self._thread_docs.pop(tid, None)
        self._thread_chunks.pop(tid, None)
        self._thread_retrievers.pop(tid, None)


multi_doc_manager = MultiDocManager()
