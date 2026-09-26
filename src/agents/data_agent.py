"""Specialized Data Analyst Agent.

Performs data transformation, statistical summarization, CSV/tabular evaluation,
and safe read-only SQL queries with structured chart-ready outputs.
"""
from __future__ import annotations

from typing import Any
from langchain_core.tools import tool

from agent_tools import analyze_tabular_data
from src.agents.shared_state import message_bus
from src.tools.database_tool import query_database


class DataAnalystAgent:
    """Autonomous data analytics subagent."""

    def __init__(self, name: str = "data-analyst"):
        self.name = name

    def analyze(
        self,
        task: str,
        csv_data: str = "",
        sql_query: str = "",
        thread_id: str = "global",
    ) -> dict[str, Any]:
        """Perform data analysis on CSV text or safe SQL query."""
        clean_task = task.strip()
        results: dict[str, Any] = {"task": clean_task, "status": "in_progress"}

        # 1. Analyze tabular data if CSV provided
        if csv_data.strip():
            try:
                table_res = analyze_tabular_data.invoke({"data": csv_data})
                results["tabular_analysis"] = table_res
            except Exception as exc:
                results["tabular_error"] = str(exc)

        # 2. Run read-only SQL query if provided
        if sql_query.strip():
            try:
                sql_res = query_database.invoke({"query": sql_query})
                results["sql_result"] = sql_res
            except Exception as exc:
                results["sql_error"] = str(exc)

        results["status"] = "completed"

        # Dispatch report via message bus
        content_summary = f"Analysis for '{clean_task[:40]}' completed."
        message_bus.send_message(
            sender=self.name,
            recipient="supervisor",
            content=content_summary,
            summary=f"Data analysis for {clean_task[:30]}",
            thread_id=thread_id,
            artifacts=[results],
        )

        return results


data_analyst_agent = DataAnalystAgent()


@tool
def run_data_analysis(
    task: str,
    csv_data: str = "",
    sql_query: str = "",
    thread_id: str = "global",
) -> dict[str, Any]:
    """Delegate tabular, statistical, or database analytical work to the Data Analyst Agent.

    Args:
        task: Objective or question to answer from the data.
        csv_data: Raw CSV table data string to parse and summarize.
        sql_query: Read-only SQL query to run against system database.
        thread_id: Context thread ID.
    """
    return data_analyst_agent.analyze(
        task=task,
        csv_data=csv_data,
        sql_query=sql_query,
        thread_id=thread_id,
    )
