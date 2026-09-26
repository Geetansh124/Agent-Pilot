"""Extended toolset for modern Agentic AI and LLM workflows.

Includes code execution, URL fetching, temporal grounding, and data analysis.
"""
from __future__ import annotations

import datetime
import io
import json
import re
import sys
import traceback
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from langchain_core.tools import tool


@tool
def get_current_datetime(timezone_name: str = "UTC") -> dict[str, Any]:
    """Get the current live date, time, day of the week, and year.
    
    Use whenever a question depends on today's date, current year, or elapsed time.
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    return {
        "utc_iso": now_utc.isoformat(),
        "date": now_utc.strftime("%Y-%m-%d"),
        "time_utc": now_utc.strftime("%H:%M:%S"),
        "day_of_week": now_utc.strftime("%A"),
        "year": now_utc.year,
        "timezone": timezone_name,
    }


@tool
def fetch_web_url(url: str) -> dict[str, Any]:
    """Fetch and read the text content of any public web page or API URL.
    
    Extracts clean readable text by stripping HTML tags, scripts, and styling.
    """
    parsed = urlparse(url)
    if not parsed.scheme or parsed.scheme not in ("http", "https"):
        return {"error": "Invalid URL scheme. Must start with http:// or https://", "url": url}

    try:
        headers = {
            "User-Agent": "DocuPilotAI-Bot/1.0 (+https://docupilot-api.onrender.com)",
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9",
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()
        if "application/json" in content_type:
            try:
                data = response.json()
                return {"url": url, "type": "json", "data": data}
            except Exception:
                pass

        raw_text = response.text
        # Extract title if present
        title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_text, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Remove scripts, styles, and tags
        text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", raw_text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        clean_text = " ".join(text.split())

        return {
            "url": url,
            "status_code": response.status_code,
            "title": title,
            "content": clean_text[:4000],
            "total_chars": len(clean_text),
        }
    except requests.RequestException as exc:
        return {"error": f"Failed to fetch URL: {exc}", "url": url}


@tool
def python_interpreter(code: str) -> dict[str, Any]:
    """Execute Python code in a safe sandbox to compute answers, process data, or verify logic.
    
    Standard libraries (math, datetime, json, re) are pre-imported. Prints to stdout are captured.
    """
    restricted_keywords = ["import os", "import sys", "subprocess", "shutil", "__import__", "eval(", "exec("]
    for kw in restricted_keywords:
        if kw in code:
            return {"error": f"Execution of dangerous keyword '{kw}' is restricted.", "success": False}

    stdout_buffer = io.StringIO()
    safe_globals = {
        "__builtins__": {
            "print": lambda *args, **kwargs: print(*args, file=stdout_buffer, **kwargs),
            "range": range,
            "len": len,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "min": min,
            "max": max,
            "sum": sum,
            "abs": abs,
            "round": round,
            "enumerate": enumerate,
            "zip": zip,
            "sorted": sorted,
            "reversed": reversed,
            "isinstance": isinstance,
        },
        "math": __import__("math"),
        "datetime": datetime,
        "json": json,
        "re": re,
    }
    local_vars: Dict[str, Any] = {}

    try:
        old_stdout = sys.stdout
        sys.stdout = stdout_buffer
        try:
            exec(code, safe_globals, local_vars)
        finally:
            sys.stdout = old_stdout

        output = stdout_buffer.getvalue()
        serializable_locals = {
            k: repr(v)[:200] for k, v in local_vars.items() if not k.startswith("_")
        }
        return {
            "success": True,
            "stdout": output.strip(),
            "variables": serializable_locals,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=2),
        }


@tool
def analyze_tabular_data(data: str) -> dict[str, Any]:
    """Analyze tabular CSV or JSON data to compute statistics, columns, and data profiles.
    
    Accepts CSV text or JSON array text and returns row counts, column metrics, and summaries.
    """
    rows: list[dict[str, Any]] = []
    data_clean = data.strip()

    if data_clean.startswith("[") or data_clean.startswith("{"):
        try:
            parsed = json.loads(data_clean)
            if isinstance(parsed, list):
                rows = [item for item in parsed if isinstance(item, dict)]
            elif isinstance(parsed, dict):
                rows = [parsed]
        except Exception as exc:
            return {"error": f"Invalid JSON format: {exc}"}
    else:
        # Parse CSV
        lines = [l.strip() for l in data_clean.split("\n") if l.strip()]
        if len(lines) < 2:
            return {"error": "CSV must have at least a header row and one data row."}
        headers = [h.strip().strip('"') for h in lines[0].split(",")]
        for line in lines[1:]:
            values = [v.strip().strip('"') for v in line.split(",")]
            rows.append(dict(zip(headers, values)))

    if not rows:
        return {"error": "No tabular rows found."}

    columns = list(rows[0].keys())
    stats: dict[str, Any] = {}
    for col in columns:
        vals = [r.get(col) for r in rows if col in r]
        # Check if numerical
        num_vals = []
        for v in vals:
            try:
                if v is not None:
                    num_vals.append(float(v))
            except (ValueError, TypeError):
                pass

        if len(num_vals) == len(vals) and num_vals:
            stats[col] = {
                "type": "numeric",
                "count": len(num_vals),
                "min": min(num_vals),
                "max": max(num_vals),
                "avg": round(sum(num_vals) / len(num_vals), 2),
            }
        else:
            unique_count = len(set(str(v) for v in vals))
            stats[col] = {
                "type": "categorical/text",
                "count": len(vals),
                "unique": unique_count,
            }

    return {
        "total_rows": len(rows),
        "total_columns": len(columns),
        "columns": columns,
        "summary": stats,
    }


def _route_with_ruflo(task: str) -> dict:
    """Route a request through the project-local Ruflo MCP tool."""
    import os
    import shutil
    import subprocess

    extra_paths = [
        os.path.dirname(shutil.which("node") or ""),
        r"C:\Program Files\nodejs",
        r"C:\Program Files (x86)\nodejs",
        os.path.expanduser(r"~\AppData\Roaming\npm"),
        os.path.expanduser("~/.local/node-v20.20.2/current/bin"),
        "/usr/local/bin",
        "/usr/bin",
    ]
    current_path = os.environ.get("PATH", "")
    path_dirs = [p for p in extra_paths if p and os.path.isdir(p)] + [current_path]
    full_path = os.pathsep.join(dict.fromkeys(path_dirs))
    env = {**os.environ, "PATH": full_path}

    npx_bin = shutil.which("npx.cmd", path=full_path) or shutil.which("npx", path=full_path) or "npx"
    command = [
        npx_bin,
        "--yes",
        "ruflo",
        "mcp",
        "exec",
        "-t",
        "hooks_route",
        "-p",
        json.dumps({"task": task}),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            shell=(os.name == "nt"),
        )
    except subprocess.TimeoutExpired:
        return {"error": "Ruflo routing timed out after 30 seconds.", "task": task}
    except OSError as exc:
        return {"error": f"Ruflo is unavailable: {exc}", "task": task}

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        return {
            "error": f"Ruflo routing failed (exit {completed.returncode}): {detail}",
            "task": task,
        }

    marker = "Result:"
    output = completed.stdout
    if marker not in output:
        return {
            "error": "Ruflo returned no routing result.",
            "task": task,
            "raw_output": output[-2000:],
        }
    try:
        return json.loads(output.split(marker, 1)[1].strip())
    except json.JSONDecodeError as exc:
        return {
            "error": f"Ruflo returned invalid routing JSON: {exc}",
            "task": task,
            "raw_output": output[-2000:],
        }


@tool
def ruflo_route(task: str) -> dict:
    """Route a task through Ruflo's semantic agent router."""
    return _route_with_ruflo(task)
