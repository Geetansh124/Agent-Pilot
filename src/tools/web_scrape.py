"""Structured web scraping tool using BeautifulSoup and requests.

Extracts titles, meta tags, headings, structured text paragraphs, links, and tables.
Includes SSRF boundary protection and payload size limits.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests
from langchain_core.tools import tool


def _is_safe_url(url: str) -> tuple[bool, str]:
    """Validate that the URL is public and not targeting local/private loopback."""
    try:
        parsed = urlparse(url)
    except Exception as exc:
        return False, f"Malformed URL: {exc}"

    if parsed.scheme not in ("http", "https"):
        return False, "URL scheme must be http or https"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL is missing a valid hostname"

    lower_host = hostname.lower()
    if lower_host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return False, "Access to localhost and loopback interfaces is prohibited"

    try:
        ip = ipaddress.ip_address(lower_host)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            return False, "Access to private/internal networks is prohibited"
    except ValueError:
        # Host is a domain name, acceptable
        pass

    return True, ""


@tool
def scrape_web(url: str, max_chars: int = 10000) -> dict[str, Any]:
    """Extract clean, structured content from a public web page URL.

    Parses page title, meta description, headings, readable text paragraphs,
    key hyperlinks, and tables while stripping ads, scripts, and navigation chrome.
    """
    safe, reason = _is_safe_url(url)
    if not safe:
        return {"error": reason, "url": url}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Agent-Pilot/1.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        return {"error": f"Failed to fetch URL: {exc}", "url": url}

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove non-content tags
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    if meta_tag and isinstance(meta_tag, dict) and meta_tag.get("content"):
        meta_desc = str(meta_tag["content"]).strip()

    headings = []
    for h in soup.find_all(["h1", "h2", "h3"]):
        text = h.get_text(strip=True)
        if text:
            headings.append(f"{h.name.upper()}: {text}")

    # Extract tables
    tables_data = []
    for table in soup.find_all("table")[:3]:
        rows = []
        for tr in table.find_all("tr")[:15]:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            tables_data.append("\n".join(rows))

    # Extract clean paragraph text
    paragraphs = []
    for p in soup.find_all(["p", "article", "section"]):
        p_text = p.get_text(" ", strip=True)
        if len(p_text) > 40 and p_text not in paragraphs:
            paragraphs.append(p_text)

    body_text = "\n\n".join(paragraphs) if paragraphs else soup.get_text(" ", strip=True)
    body_text = re.sub(r"\s+", " ", body_text).strip()

    # Extract top links
    links = []
    for a in soup.find_all("a", href=True)[:15]:
        href = urljoin(url, a["href"])
        anchor = a.get_text(strip=True)
        if anchor and href.startswith("http") and href != url:
            links.append({"text": anchor[:60], "url": href})

    char_limit = max(500, min(int(max_chars), 30000))
    truncated = len(body_text) > char_limit
    return {
        "url": url,
        "title": title,
        "description": meta_desc,
        "headings": headings[:15],
        "tables": tables_data,
        "links": links[:10],
        "content": body_text[:char_limit],
        "truncated": truncated,
        "total_chars": len(body_text),
    }
