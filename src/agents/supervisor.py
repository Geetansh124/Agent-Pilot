"""Top-level Supervisor and Routing Agent.

Analyzes incoming user tasks, determines the optimal specialist agent,
coordinates multi-agent delegation pipelines, and aggregates findings.
"""
from __future__ import annotations

import re
from typing import Any
from langchain_core.tools import tool


from src.agents.coding_agent import coding_agent
from src.agents.data_agent import data_analyst_agent
from src.agents.research_agent import research_agent
from src.agents.testing_agent import testing_agent
from src.agents.shared_state import AgentRole, message_bus


class SupervisorAgent:
    """Supervisor coordinating specialist subagents."""

    def __init__(self, name: str = "supervisor"):
        self.name = name

    def classify_intent(self, task: str) -> AgentRole:
        """Classify task into specialized domain using token boundaries."""
        t = task.lower()
        words = set(re.findall(r"\b\w+\b", t))
        if any(w in words for w in ("test", "tests", "pytest", "coverage", "assert", "mock")) or "unit test" in t:
            return AgentRole.TESTING
        if any(w in words for w in ("code", "function", "script", "python", "bug", "refactor", "syntax", "file")) or "write file" in t:
            return AgentRole.CODER
        if any(w in words for w in ("csv", "table", "sql", "database", "query", "columns", "rows", "statistics", "dataset")):
            return AgentRole.DATA_ANALYST
        if any(w in words for w in ("search", "find", "research", "scrape", "lookup", "news")) or "who is" in t or "what is" in t:
            return AgentRole.RESEARCHER
        return AgentRole.GENERAL


    def delegate(
        self,
        task: str,
        thread_id: str = "global",
        role: str = "auto",
        code: str = "",
        filename: str = "",
        csv_data: str = "",
        sql_query: str = "",
    ) -> dict[str, Any]:
        """Route task to specialist agent and return structured output."""
        clean_task = task.strip()
        assigned_role = AgentRole(role) if role in [r.value for r in AgentRole] and role != "auto" else self.classify_intent(clean_task)

        # Notify recipient on message bus
        message_bus.send_message(
            sender=self.name,
            recipient=assigned_role.value,
            content=clean_task,
            summary=f"Delegating task to {assigned_role.value}",
            thread_id=thread_id,
        )

        if assigned_role == AgentRole.RESEARCHER:
            res = research_agent.research(topic=clean_task, thread_id=thread_id)
            output = res.get("report", "")
        elif assigned_role == AgentRole.CODER:
            res = coding_agent.execute_task(task=clean_task, thread_id=thread_id, code=code, filename=filename)
            output = str(res)
        elif assigned_role == AgentRole.TESTING:
            res = testing_agent.run_tests_or_generate(task=clean_task, filename=filename, thread_id=thread_id)
            output = str(res)
        elif assigned_role == AgentRole.DATA_ANALYST:
            res = data_analyst_agent.analyze(task=clean_task, csv_data=csv_data, sql_query=sql_query, thread_id=thread_id)
            output = str(res)
        else:
            res = {"task": clean_task, "response": "Handled by general assistant."}
            output = res["response"]

        return {
            "task": clean_task,
            "assigned_agent": assigned_role.value,
            "delegation_output": output,
            "result_details": res,
            "status": "completed",
        }


supervisor_agent = SupervisorAgent()


@tool
def route_to_specialist(
    task: str,
    thread_id: str = "global",
    role: str = "auto",
    code: str = "",
    filename: str = "",
    csv_data: str = "",
    sql_query: str = "",
) -> dict[str, Any]:
    """Delegate work to a specialized sub-agent (researcher, coder, data-analyst).

    Args:
        task: Description of the subtask or question.
        thread_id: Context conversation thread ID.
        role: Target agent role ('auto', 'researcher', 'coder', 'data-analyst', 'general').
        code: Optional code snippet if delegating to coder.
        filename: Optional target filename for code or file operations.
        csv_data: Optional CSV text for data analysis.
        sql_query: Optional SQL query for data analyst.
    """
    return supervisor_agent.delegate(
        task=task,
        thread_id=thread_id,
        role=role,
        code=code,
        filename=filename,
        csv_data=csv_data,
        sql_query=sql_query,
    )
