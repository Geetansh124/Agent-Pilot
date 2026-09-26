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

    def get_hybrid_retriever(self, thread_id: str) -> Optional[HybridRetriever]:
        """Return the active hybrid retriever for the thread."""
        tid = str(thread_id)
        return self._thread_retrievers.get(tid)

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
