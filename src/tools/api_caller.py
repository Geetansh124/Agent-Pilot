"""Generic REST API caller tool with security and SSRF safeguards.

Enables the agent to interact with external public web APIs (GET, POST, PUT, DELETE, PATCH)
with structured parameter passing, strict timeouts, and boundary guards.
"""
from __future__ import annotations

import ipaddress
import json
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from langchain_core.tools import tool


def _validate_api_url(url: str) -> tuple[bool, str]:
    """Validate that the target URL is safe for outbound API requests."""
    try:
        parsed = urlparse(url)
    except Exception as exc:
        return False, f"Malformed URL: {exc}"

    if parsed.scheme not in ("http", "https"):
        return False, "Protocol must be HTTP or HTTPS."

    host = parsed.hostname
    if not host:
        return False, "URL missing valid hostname."

    lower_host = host.lower()
    if lower_host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return False, "Access to localhost/loopback interfaces is forbidden."

    try:
        ip = ipaddress.ip_address(lower_host)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            return False, "Outbound calls to private/internal networks are forbidden."
    except ValueError:
        pass

    return True, ""


@tool
def call_api(
    url: str,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Make an HTTP request to any external public REST API.

    Args:
        url: The full target URL (must begin with http:// or https://).
        method: HTTP method — GET, POST, PUT, DELETE, or PATCH (default GET).
        headers: Optional key-value dictionary of HTTP request headers.
        params: Optional dictionary of query parameters to append to the URL.
        json_body: Optional dictionary representing JSON request body.
    """
    valid, reason = _validate_api_url(url)
    if not valid:
        return {"error": reason, "url": url, "success": False}

    clean_method = method.strip().upper()
    if clean_method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
        return {"error": f"Unsupported HTTP method: {method}", "success": False}

    req_headers = {"User-Agent": "AgentPilot-RESTClient/1.0", "Accept": "application/json, text/plain, */*"}
    if headers and isinstance(headers, dict):
        req_headers.update({str(k): str(v) for k, v in headers.items()})

    try:
        resp = requests.request(
            method=clean_method,
            url=url,
            headers=req_headers,
            params=params,
            json=json_body if json_body and clean_method in ("POST", "PUT", "PATCH") else None,
            timeout=20,
        )

        content_type = resp.headers.get("content-type", "").lower()
        is_json = "application/json" in content_type
        parsed_data = None
        if is_json:
            try:
                parsed_data = resp.json()
            except Exception:
                parsed_data = resp.text[:10000]
        else:
            parsed_data = resp.text[:10000]

        return {
            "status_code": resp.status_code,
            "url": str(resp.url),
            "content_type": content_type,
            "data": parsed_data,
            "success": resp.ok,
        }
    except requests.exceptions.Timeout:
        return {"error": "API request timed out after 20 seconds.", "url": url, "success": False}
    except requests.exceptions.RequestException as exc:
        return {"error": f"API request failed: {exc}", "url": url, "success": False}
