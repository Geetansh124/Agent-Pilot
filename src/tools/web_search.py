"""Web search tool supporting Tavily with DuckDuckGo fallback.

Provides high-relevance search snippets, direct source URLs, and structured answers.
"""
from __future__ import annotations

import os
from typing import Any
import requests
from langchain_core.tools import tool


@tool
def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search the public web for real-time information, news, documentation, or facts.

    Uses Tavily API if configured, otherwise falls back to DuckDuckGo search.
    Returns structured results containing title, url, content snippet, and source score.
    """
    clean_query = query.strip()
    if not clean_query:
        return {"error": "Query cannot be empty", "query": query, "results": []}

    max_results = max(1, min(int(max_results), 10))

    # 1. Try Tavily if key is available
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": clean_query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    "include_answer": True,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", ""),
                        "score": r.get("score", 0.0),
                    }
                    for r in data.get("results", [])
                ]
                return {
                    "provider": "tavily",
                    "query": clean_query,
                    "answer": data.get("answer"),
                    "results": results,
                }
        except Exception:
            # Fall through to DuckDuckGo fallback
            pass

    # 2. DuckDuckGo fallback
    try:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for item in ddgs.text(clean_query, max_results=max_results):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("href", ""),
                    "content": item.get("body", ""),
                    "score": 1.0,
                })
        return {
            "provider": "duckduckgo",
            "query": clean_query,
            "results": results,
        }
    except Exception as exc:
        return {
            "provider": "none",
            "error": f"Search failed: {exc}",
            "query": clean_query,
            "results": [],
        }
