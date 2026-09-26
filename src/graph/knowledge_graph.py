"""Knowledge Graph extraction, storage, and traversal engine.

Extracts entities and semantic relationships (triples) from text, stores them in
an indexed SQLite property graph, and provides multi-hop subgraph querying.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Optional
from langchain_core.tools import tool

DB_PATH = "chatbot.db"


def _get_graph_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS graph_nodes (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            properties TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS graph_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            properties TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_id) REFERENCES graph_nodes(id),
            FOREIGN KEY (target_id) REFERENCES graph_nodes(id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_source ON graph_edges (source_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_target ON graph_edges (target_id)")
    conn.commit()
    return conn


class KnowledgeGraph:
    """Property graph supporting entity-relation triples and subgraph traversal."""

    def __init__(self, db_path: str = DB_PATH):
        self.conn = _get_graph_conn(db_path)

    def add_node(self, node_id: str, label: str, entity_type: str = "concept", properties: Optional[dict[str, Any]] = None) -> None:
        """Insert or update a graph node."""
        nid = node_id.strip().lower()
        lbl = label.strip()
        etype = entity_type.strip().lower()
        props = json.dumps(properties or {})
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO graph_nodes (id, label, entity_type, properties)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET label = excluded.label, entity_type = excluded.entity_type, properties = excluded.properties""",
            (nid, lbl, etype, props),
        )
        self.conn.commit()

    def add_edge(self, source: str, relation: str, target: str, weight: float = 1.0, properties: Optional[dict[str, Any]] = None) -> None:
        """Create a directed edge between two entities."""
        src = source.strip().lower()
        tgt = target.strip().lower()
        rel = relation.strip().upper()
        # Ensure nodes exist
        self.add_node(src, source, "entity")
        self.add_node(tgt, target, "entity")

        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO graph_edges (source_id, target_id, relation, weight, properties)
               VALUES (?, ?, ?, ?, ?)""",
            (src, tgt, rel, weight, json.dumps(properties or {})),
        )
        self.conn.commit()

    def query_subgraph(self, entity: str, max_depth: int = 2) -> dict[str, Any]:
        """Traverse outbound and inbound relations for an entity up to max_depth."""
        root = entity.strip().lower()
        cursor = self.conn.cursor()

        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        visited = set()
        queue = [(root, 0)]

        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)

            # Fetch node info
            cursor.execute("SELECT id, label, entity_type, properties FROM graph_nodes WHERE id = ?", (current,))
            row = cursor.fetchone()
            if row:
                nodes[current] = {
                    "id": row[0],
                    "label": row[1],
                    "type": row[2],
                    "properties": json.loads(row[3]) if row[3] else {},
                }

            if depth < max_depth:
                # Outbound edges
                cursor.execute("SELECT source_id, target_id, relation, weight FROM graph_edges WHERE source_id = ?", (current,))
                for s, t, r, w in cursor.fetchall():
                    edges.append({"source": s, "target": t, "relation": r, "weight": w})
                    if t not in visited:
                        queue.append((t, depth + 1))

                # Inbound edges
                cursor.execute("SELECT source_id, target_id, relation, weight FROM graph_edges WHERE target_id = ?", (current,))
                for s, t, r, w in cursor.fetchall():
                    edges.append({"source": s, "target": t, "relation": r, "weight": w})
                    if s not in visited:
                        queue.append((s, depth + 1))

        return {
            "root": root,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "nodes": list(nodes.values()),
            "edges": edges,
        }

    def extract_triples_from_text(self, text: str) -> list[tuple[str, str, str]]:
        """Heuristic rule-based extraction of (Subject, Relation, Object) triples."""
        triples: list[tuple[str, str, str]] = []
        patterns = [
            (r"\b([A-Z][a-zA-Z0-9_]+)\s+uses\s+([A-Z][a-zA-Z0-9_]+)\b", "USES"),
            (r"\b([A-Z][a-zA-Z0-9_]+)\s+is\s+a\s+([a-zA-Z0-9_]+)\b", "IS_A"),
            (r"\b([A-Z][a-zA-Z0-9_]+)\s+implements\s+([A-Z][a-zA-Z0-9_]+)\b", "IMPLEMENTS"),
            (r"\b([A-Z][a-zA-Z0-9_]+)\s+contains\s+([A-Z][a-zA-Z0-9_]+)\b", "CONTAINS"),
        ]
        for pattern, rel in patterns:
            for match in re.finditer(pattern, text):
                sub, obj = match.group(1), match.group(2)
                triples.append((sub, rel, obj))
                self.add_edge(sub, rel, obj)
        return triples


knowledge_graph = KnowledgeGraph()


@tool
def query_knowledge_graph(entity: str) -> dict[str, Any]:
    """Query semantic relations and connected nodes for an entity from the knowledge graph.

    Args:
        entity: The entity name or concept (e.g. 'LangGraph', 'FAISS', 'FastAPI').
    """
    return knowledge_graph.query_subgraph(entity=entity, max_depth=2)
