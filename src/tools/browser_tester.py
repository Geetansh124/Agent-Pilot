"""Browser and Web Application Testing Tool.

Provides automated HTTP and DOM validation for generated web applications,
verifying endpoints, title tags, semantic HTML structure, and response health.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Optional
import urllib.request
import urllib.error

from langchain_core.tools import tool


@dataclass
class BrowserTestResult:
    target_url: str
    status_code: int
    is_accessible: bool
    title: str = ""
    headings: list[str] = None
    has_viewport_meta: bool = False
    errors: list[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["headings"] = d["headings"] or []
        d["errors"] = d["errors"] or []
        return d


class BrowserTester:
    """Validates web page structure and HTTP reachability."""

    def test_page(self, url: str, timeout: float = 5.0) -> BrowserTestResult:
        """Fetch and inspect a web page for basic HTML correctness and accessibility."""
        import time
        start = time.monotonic()
        errors = []

        if not url.startswith(("http://", "https://")):
            url = "http://" + url

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AgentPilot-BrowserTester/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = response.status
                html_bytes = response.read(100000)  # Read up to 100KB
                html_text = html_bytes.decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as exc:
            duration = round((time.monotonic() - start) * 1000, 2)
            return BrowserTestResult(
                target_url=url,
                status_code=exc.code,
                is_accessible=False,
                errors=[f"HTTP Error {exc.code}: {exc.reason}"],
                duration_ms=duration,
            )
        except Exception as exc:
            duration = round((time.monotonic() - start) * 1000, 2)
            return BrowserTestResult(
                target_url=url,
                status_code=0,
                is_accessible=False,
                errors=[f"Connection failed: {str(exc)}"],
                duration_ms=duration,
            )

        duration = round((time.monotonic() - start) * 1000, 2)

        # Extract title
        title_match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Extract headings (h1, h2)
        headings = re.findall(r"<h[1-2][^>]*>(.*?)</h[1-2]>", html_text, re.IGNORECASE | re.DOTALL)
        clean_headings = [re.sub(r"<[^>]+>", "", h).strip() for h in headings[:10]]

        # Check viewport meta tag
        has_viewport = bool(re.search(r'<meta[^>]+name=[\'"]viewport[\'"]', html_text, re.IGNORECASE))

        if not title:
            errors.append("Warning: Missing <title> tag.")
        if not has_viewport:
            errors.append("Warning: Missing responsive <meta name='viewport'> tag.")

        return BrowserTestResult(
            target_url=url,
            status_code=status_code,
            is_accessible=status_code == 200,
            title=title,
            headings=clean_headings,
            has_viewport_meta=has_viewport,
            errors=errors,
            duration_ms=duration,
        )

    def test_dom_string(self, html_content: str) -> dict[str, Any]:
        """Validate an HTML string directly for SEO and accessibility tags."""
        title_match = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        headings = re.findall(r"<h[1-2][^>]*>(.*?)</h[1-2]>", html_content, re.IGNORECASE | re.DOTALL)
        clean_headings = [re.sub(r"<[^>]+>", "", h).strip() for h in headings[:10]]
        has_viewport = bool(re.search(r'<meta[^>]+name=[\'"]viewport[\'"]', html_content, re.IGNORECASE))

        issues = []
        if not title:
            issues.append("Missing <title> tag.")
        if not has_viewport:
            issues.append("Missing responsive viewport meta tag.")

        return {
            "valid_html": bool(html_content.strip()),
            "title": title,
            "headings": clean_headings,
            "has_viewport_meta": has_viewport,
            "issues": issues,
            "quality_score": max(100 - len(issues) * 20, 0),
        }


browser_tester = BrowserTester()


@tool
def test_web_endpoint(url: str) -> dict[str, Any]:
    """Test a web endpoint or application URL for accessibility, status code, and semantic tags.

    Args:
        url: The web URL to verify.
    """
    res = browser_tester.test_page(url)
    return res.to_dict()
