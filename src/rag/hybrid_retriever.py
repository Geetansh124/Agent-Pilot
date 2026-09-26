"""Hybrid search retriever combining dense vector retrieval and BM25 token-matching.

Implements Reciprocal Rank Fusion (RRF) to re-rank results and generates
high-fidelity source citations with chunk provenance, page numbers, and confidence.
"""
from __future__ import annotations

import re
from typing import Any, Sequence
from langchain_core.documents import Document


def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase alphanumeric terms."""
    return set(re.findall(r"\b[a-zA-Z0-9_]{2,}\b", text.lower()))


def bm25_sparse_score(query_tokens: set[str], doc_text: str) -> float:
    """Compute sparse lexical overlap score between query terms and document content."""
    if not query_tokens or not doc_text:
        return 0.0
    doc_tokens = re.findall(r"\b[a-zA-Z0-9_]{2,}\b", doc_text.lower())
    if not doc_tokens:
        return 0.0
    doc_len = len(doc_tokens)
    matches = sum(1 for tok in doc_tokens if tok in query_tokens)
    return matches / (doc_len + 10.0)


class HybridRetriever:
    """Hybrid search combining dense vector search and sparse keyword matching with RRF."""

    def __init__(self, vector_store: Any, all_documents: Sequence[Document] | None = None, rrf_k: int = 60):
        self.vector_store = vector_store
        self.all_documents = list(all_documents or [])
        self.rrf_k = rrf_k

    def add_documents(self, documents: Sequence[Document]) -> None:
        """Register additional documents for sparse matching."""
        self.all_documents.extend(documents)

    def retrieve(
        self,
        query: str,
        k: int = 5,
        dense_fetch_k: int = 15,
        sparse_weight: float = 0.3,
        dense_weight: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Perform hybrid retrieval with Reciprocal Rank Fusion (RRF).

        Returns:
            List of dicts containing 'document', 'content', 'citation', 'metadata', and 'score'.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        # 1. Dense retrieval via vector store MMR or similarity search
        try:
            dense_docs = self.vector_store.max_marginal_relevance_search(
                clean_query, k=dense_fetch_k, fetch_k=dense_fetch_k * 2
            )
        except Exception:
            try:
                dense_docs = self.vector_store.similarity_search(clean_query, k=dense_fetch_k)
            except Exception:
                dense_docs = []

        # 2. Sparse retrieval via keyword overlap across all registered documents
        query_terms = _tokenize(clean_query)
        scored_sparse = []
        candidate_docs = self.all_documents if self.all_documents else dense_docs
        for doc in candidate_docs:
            score = bm25_sparse_score(query_terms, doc.page_content)
            if score > 0:
                scored_sparse.append((score, doc))

        scored_sparse.sort(key=lambda x: x[0], reverse=True)
        sparse_docs = [doc for _, doc in scored_sparse[:dense_fetch_k]]

        # 3. Reciprocal Rank Fusion (RRF)
        doc_scores: dict[str, float] = {}
        doc_map: dict[str, Document] = {}

        def _doc_key(d: Document) -> str:
            return f"{d.metadata.get('source', '')}:{d.metadata.get('page', 0)}:{d.page_content[:50]}"

        for rank, doc in enumerate(dense_docs):
            key = _doc_key(doc)
            doc_map[key] = doc
            rrf_score = dense_weight * (1.0 / (self.rrf_k + rank + 1))
            doc_scores[key] = doc_scores.get(key, 0.0) + rrf_score

        for rank, doc in enumerate(sparse_docs):
            key = _doc_key(doc)
            doc_map[key] = doc
            rrf_score = sparse_weight * (1.0 / (self.rrf_k + rank + 1))
            doc_scores[key] = doc_scores.get(key, 0.0) + rrf_score

        # Sort by final fused RRF score
        sorted_keys = sorted(doc_scores.keys(), key=lambda k: doc_scores[k], reverse=True)

        results: list[dict[str, Any]] = []
        for key in sorted_keys[:k]:
            doc = doc_map[key]
            meta = doc.metadata or {}
            source = meta.get("filename") or meta.get("source") or "document"
            page = meta.get("page", 0)
            page_str = f"Page {page + 1}" if isinstance(page, int) else f"Section {page}"
            chunk_id = meta.get("chunk_id", "chunk")
            citation = f"[{source}, {page_str}]"

            results.append(
                {
                    "content": doc.page_content,
                    "citation": citation,
                    "source": source,
                    "page": page,
                    "metadata": meta,
                    "score": round(doc_scores[key], 4),
                }
            )

        return results
