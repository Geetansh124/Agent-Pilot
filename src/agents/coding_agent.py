"""Specialized Coding Agent.

Manages workspace code files, performs syntax verification, executes Python scripts,
and runs diagnostics in the thread-sandboxed workspace environment.
"""
from __future__ import annotations

import ast
from typing import Any
from langchain_core.tools import tool

from agent_tools import python_interpreter
from src.agents.shared_state import message_bus
from src.tools.file_tools import (
    list_workspace_files,
    read_workspace_file,
    write_workspace_file,
)


class CodingAgent:
    """Autonomous software engineering subagent."""

    def __init__(self, name: str = "coder"):
        self.name = name

    def execute_task(
        self,
        task: str,
        thread_id: str = "global",
        filename: str = "",
        code: str = "",
        run_code: bool = True,
    ) -> dict[str, Any]:
        """Execute a coding or file modification task."""
        clean_task = task.strip()
        results: dict[str, Any] = {"task": clean_task, "status": "in_progress"}

        # 1. If code is provided, validate syntax
        if code:
            try:
                ast.parse(code)
                results["syntax_valid"] = True
            except SyntaxError as err:
                results["syntax_valid"] = False
                results["syntax_error"] = str(err)
                return results

            # Write code to sandboxed workspace if filename provided
            target_name = filename.strip() or "solution.py"
            write_res = write_workspace_file.invoke({
                "filename": target_name,
                "content": code,
                "thread_id": thread_id,
            })
            results["file_written"] = write_res

            # Optionally execute the code
            if run_code:
                try:
                    exec_res = python_interpreter.invoke({"code": code})
                    results["execution"] = exec_res
                except Exception as exc:
                    results["execution_error"] = str(exc)

        # 2. Inspect workspace
        files_res = list_workspace_files.invoke({"thread_id": thread_id})
        results["workspace_files"] = files_res.get("files", [])
        results["status"] = "completed"

        # Report to supervisor via message bus
        summary_text = (
            f"Coding task '{clean_task[:40]}' completed. "
            + (f"Execution output: {str(results.get('execution', ''))[:150]}" if run_code and code else "Workspace synced.")
        )
        message_bus.send_message(
            sender=self.name,
            recipient="supervisor",
            content=summary_text,
            summary=f"Code output for {clean_task[:30]}",
            thread_id=thread_id,
            artifacts=[results],
        )

        return results


coding_agent = CodingAgent()


@tool
def run_code_task(
    task: str,
    thread_id: str = "global",
    filename: str = "",
    code: str = "",
    run_code: bool = True,
) -> dict[str, Any]:
    """Delegate a software engineering, code generation, or testing task to the Coding Agent.

    Args:
        task: Description of the engineering task.
        thread_id: Workspace sandboxing thread ID.
        filename: Optional target file to write inside workspace.
        code: Python source code to validate, save, or run.
        run_code: Whether to execute the Python code safely in the interpreter.
    """
    return coding_agent.execute_task(
        task=task,
        thread_id=thread_id,
        filename=filename,
        code=code,
        run_code=run_code,
    )
