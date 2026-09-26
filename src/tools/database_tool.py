"""Safe SQL database inspection and querying tool.

Provides read-only SQL querying capability against SQLite databases with
strict boundary validation blocking destructive DDL and DML operations.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any
from langchain_core.tools import tool

DISALLOWED_KEYWORDS = {
    "DROP", "ALTER", "TRUNCATE", "DELETE", "UPDATE", "INSERT",
    "REPLACE", "CREATE", "ATTACH", "DETACH", "PRAGMA", "VACUUM", "GRANT", "REVOKE"
}


def _validate_sql_query(query: str) -> tuple[bool, str]:
    """Verify that the SQL query is strictly read-only and free of destructive statements."""
    clean = query.strip()
    if not clean:
        return False, "Query cannot be empty"

    # Block multiple statements (prevent stacked query injection)
    statements = [s.strip() for s in clean.split(";") if s.strip()]
    if len(statements) > 1:
        return False, "Multiple SQL statements in a single query are prohibited."

    first_statement = statements[0] if statements else clean
    tokens = re.findall(r"\b[A-Za-z_]+\b", first_statement.upper())
    if not tokens:
        return False, "Invalid SQL syntax."

    first_word = tokens[0]
    if first_word not in ("SELECT", "WITH", "EXPLAIN"):
        return False, f"Prohibited operation: only read-only queries (SELECT, WITH, EXPLAIN) are permitted. Found: '{first_word}'."

    # Check for any prohibited mutation keywords anywhere in query
    for token in tokens:
        if token in DISALLOWED_KEYWORDS:
            return False, f"Prohibited SQL keyword detected: '{token}'."

    return True, ""


@tool
def query_database(query: str, db_name: str = "chatbot.db") -> dict[str, Any]:
    """Execute a safe, read-only SQL query against the system database.

    Args:
        query: A read-only SQL SELECT or WITH statement.
        db_name: Target database filename (defaults to 'chatbot.db').
    """
    valid, reason = _validate_sql_query(query)
    if not valid:
        return {"error": reason, "query": query, "success": False}

    safe_db = "chatbot.db" if db_name in ("chatbot.db", "", None) else "chatbot.db"
    try:
        conn = sqlite3.connect(f"file:{safe_db}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(100)
        conn.close()

        formatted_rows = [dict(zip(columns, r)) for r in rows]
        return {
            "query": query,
            "columns": columns,
            "row_count": len(formatted_rows),
            "rows": formatted_rows,
            "truncated": len(rows) == 100,
            "success": True,
        }
    except Exception as exc:
        return {"error": f"SQL execution error: {exc}", "query": query, "success": False}
