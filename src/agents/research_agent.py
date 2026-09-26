"""Specialized Research Agent.

Orchestrates multi-source information retrieval: web search, structured web scraping,
document RAG, and factual synthesis with source citation tracking.
"""
from __future__ import annotations

from typing import Any
from langchain_core.tools import tool

from src.agents.shared_state import message_bus
from src.rag import multi_doc_manager
from src.tools.web_scrape import scrape_web
from src.tools.web_search import web_search


class ResearchAgent:
    """Autonomous researcher subagent."""

    def __init__(self, name: str = "researcher"):
        self.name = name

    def research(
        self,
        topic: str,
        thread_id: str = "global",
        include_web: bool = True,
        include_docs: bool = True,
    ) -> dict[str, Any]:
        """Conduct research across web and document indices."""
        clean_topic = topic.strip()
        findings: list[dict[str, Any]] = []
        citations: list[str] = []

        # 1. Search indexed documents if available
        if include_docs and multi_doc_manager.has_documents(thread_id):
            retriever = multi_doc_manager.get_hybrid_retriever(thread_id)
            if retriever:
                doc_results = retriever.retrieve(clean_topic, k=3)
                for item in doc_results:
                    findings.append({
                        "source_type": "document",
                        "title": item["source"],
                        "citation": item["citation"],
                        "snippet": item["content"][:300],
                        "score": item["score"],
                    })
                    citations.append(item["citation"])

        # 2. Search web
        if include_web:
            try:
                search_results = web_search.invoke({"query": clean_topic, "max_results": 3})
                if isinstance(search_results, list):
                    for item in search_results:
                        findings.append({
                            "source_type": "web",
                            "title": item.get("title", "Web Result"),
                            "citation": f"[{item.get('title', 'Web')}]({item.get('url', '')})",
                            "snippet": item.get("snippet", "")[:300],
                            "url": item.get("url", ""),
                        })
                        citations.append(f"[{item.get('title', 'Web')}]({item.get('url', '')})")
            except Exception as exc:
                findings.append({"source_type": "web_error", "error": str(exc)})

        # Synthesize executive summary
        summary_lines = [f"### Research Findings for: {clean_topic}\n"]
        for f in findings:
            if "snippet" in f:
                summary_lines.append(f"- **{f['title']}** ({f['source_type']}): {f['snippet']}")
        if citations:
            summary_lines.append("\n**Sources Cited:** " + ", ".join(citations[:5]))

        report = "\n".join(summary_lines)

        # Send to supervisor via message bus
        message_bus.send_message(
            sender=self.name,
            recipient="supervisor",
            content=report,
            summary=f"Research on '{clean_topic[:40]}'",
            thread_id=thread_id,
            artifacts=findings,
        )

        return {
            "topic": clean_topic,
            "report": report,
            "findings_count": len(findings),
            "citations": citations,
            "findings": findings,
            "status": "completed",
        }


research_agent = ResearchAgent()


@tool
def run_research(topic: str, thread_id: str = "global") -> dict[str, Any]:
    """Delegate a deep research task to the specialized Research Agent.

    Args:
        topic: The specific inquiry, question, or technology topic to investigate.
        thread_id: Conversation thread context ID.
    """
    return research_agent.research(topic=topic, thread_id=thread_id)
