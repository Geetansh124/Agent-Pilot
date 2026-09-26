"""Graph-enhanced RAG combining knowledge graph traversal with vector retrieval.

Performs graph-hop retrieval: first finds entities in the knowledge graph related
to the query, then uses those entities to expand and enrich the vector search,
producing results that capture cross-document relationships.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from langchain_core.documents import Document
from langchain_core.tools import tool


class GraphRAG:
    """Combines knowledge graph entity lookup with hybrid vector retrieval."""

    def __init__(self, knowledge_graph: Any, hybrid_retriever: Any = None):
        self.kg = knowledge_graph
        self.retriever = hybrid_retriever

    def extract_query_entities(self, query: str) -> list[str]:
        """Extract candidate entity names from a natural language query."""
        tokens = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", query)
        keywords = re.findall(r"\b[a-zA-Z]{3,}\b", query.lower())
        stopwords = {
            "the", "and", "for", "are", "but", "not", "you", "all", "can",
            "her", "was", "one", "our", "out", "how", "what", "which", "their",
            "will", "each", "about", "them", "then", "than", "into", "from",
            "with", "that", "this", "have", "does", "been", "more", "when",
        }
        filtered = [w for w in keywords if w not in stopwords and len(w) > 3]
        return list(set(tokens + filtered[:10]))

    def graph_expand(
        self, entities: list[str], max_depth: int = 2, max_nodes: int = 20,
    ) -> list[dict[str, Any]]:
        """Traverse knowledge graph from seed entities to find related context."""
        all_related: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for entity in entities[:5]:
            entity_lower = entity.lower().strip()
            try:
                subgraph = self.kg.get_subgraph(entity_lower, depth=max_depth)
            except Exception:
                continue

            nodes = subgraph.get("nodes", [])
            edges = subgraph.get("edges", [])

            for node in nodes:
                nid = node.get("id", "")
                if nid and nid not in seen_ids:
                    seen_ids.add(nid)
                    all_related.append({
                        "entity": node.get("label", nid),
                        "type": node.get("entity_type", "concept"),
                        "source_query": entity,
                        "properties": node.get("properties", {}),
                    })
                    if len(all_related) >= max_nodes:
                        break

            for edge in edges:
                relation_ctx = (
                    f"{edge.get('source_label', '')} "
                    f"{edge.get('relation', 'RELATED_TO')} "
                    f"{edge.get('target_label', '')}"
                )
                all_related.append({
                    "entity": relation_ctx.strip(),
                    "type": "relationship",
                    "source_query": entity,
                    "relation": edge.get("relation", ""),
                    "weight": edge.get("weight", 1.0),
                })
                if len(all_related) >= max_nodes:
                    break

        return all_related

    def build_expanded_query(
        self, original_query: str, graph_context: list[dict[str, Any]]
    ) -> str:
        """Enrich the query with entity names and relationships from the graph."""
        extra_terms: list[str] = []
        for item in graph_context[:8]:
            entity = item.get("entity", "")
            if entity and len(entity) < 80:
                extra_terms.append(entity)

        if not extra_terms:
            return original_query

        expansion = " ".join(extra_terms)
        return f"{original_query} {expansion}"

    def retrieve(
        self,
        query: str,
        k: int = 5,
        graph_depth: int = 2,
        use_graph: bool = True,
    ) -> dict[str, Any]:
        """Perform graph-enhanced retrieval.

        1. Extract entities from query
        2. Traverse knowledge graph for related context
        3. Expand query with graph entities
        4. Run hybrid retrieval with expanded query
        5. Merge and deduplicate results
        """
        entities = self.extract_query_entities(query)
        graph_context: list[dict[str, Any]] = []

        if use_graph and entities and self.kg:
            graph_context = self.graph_expand(entities, max_depth=graph_depth)

        expanded_query = self.build_expanded_query(query, graph_context)

        # Vector retrieval
        retrieval_results: list[dict[str, Any]] = []
        if self.retriever:
            try:
                retrieval_results = self.retriever.retrieve(
                    expanded_query, k=k
                )
            except Exception:
                try:
                    retrieval_results = self.retriever.retrieve(query, k=k)
                except Exception:
                    pass

        # Score boost: results whose content mentions graph entities get a bonus
        if graph_context:
            entity_terms = {
                item["entity"].lower()
                for item in graph_context
                if item.get("type") != "relationship"
            }
            for result in retrieval_results:
                content = result.get("content", "").lower()
                matches = sum(1 for e in entity_terms if e in content)
                if matches > 0:
                    bonus = min(0.1 * matches, 0.3)
                    result["score"] = round(result.get("score", 0) + bonus, 4)
                    result["graph_boosted"] = True

            retrieval_results.sort(key=lambda r: r.get("score", 0), reverse=True)

        return {
            "query": query,
            "expanded_query": expanded_query,
            "entities_found": entities,
            "graph_context_count": len(graph_context),
            "graph_context": graph_context[:5],
            "results": retrieval_results[:k],
            "total_results": len(retrieval_results),
        }


@tool
def graph_enhanced_search(
    query: str, k: int = 5, graph_depth: int = 2
) -> dict[str, Any]:
    """Search documents using graph-enhanced RAG (knowledge graph + vector search).

    Expands queries using entity relationships from the knowledge graph before
    performing hybrid retrieval, improving cross-document discovery.

    Args:
        query: The search query or question.
        k: Number of results to return.
        graph_depth: How many hops to traverse in the knowledge graph.
    """
    from src.graph.knowledge_graph import knowledge_graph
    graph_rag = GraphRAG(knowledge_graph=knowledge_graph)
    return graph_rag.retrieve(query=query, k=k, graph_depth=graph_depth)


GraphRAGRetriever = GraphRAG
graph_rag_retriever = GraphRAG(knowledge_graph=None)


