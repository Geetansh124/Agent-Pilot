"""Dedicated Testing Agent for automated test generation and execution.

Analyzes code from workspace files, generates pytest test suites, detects
coverage gaps, and validates code quality through automated testing workflows.
"""
from __future__ import annotations

import ast
from typing import Any

from langchain_core.tools import tool

from src.agents.shared_state import message_bus
from src.tools.test_generator import generate_tests


class TestingAgent:
    """Agent specialized in automated test generation and code quality validation."""

    def __init__(self, name: str = "testing"):
        self.name = name

    def analyze_code(self, source_code: str, filename: str = "") -> dict[str, Any]:
        """Analyze source code for testability and generate tests."""
        if not source_code.strip():
            return {"error": "No source code provided.", "tests_generated": 0}

        # Validate syntax
        try:
            ast.parse(source_code)
        except SyntaxError as exc:
            return {
                "error": f"Syntax error in source: {exc}",
                "filename": filename,
                "tests_generated": 0,
            }

        module_name = filename.replace(".py", "").replace("/", ".") if filename else "module"
        result = generate_tests(source_code=source_code, module_name=module_name)

        # Compute coverage metrics
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            tree = None

        total_functions = 0
        testable_functions = 0
        if tree:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    total_functions += 1
                    if not node.name.startswith("_"):
                        testable_functions += 1

        result["filename"] = filename
        result["total_functions"] = total_functions
        result["testable_functions"] = testable_functions
        result["coverage_potential"] = (
            f"{(testable_functions / total_functions * 100):.0f}%"
            if total_functions > 0 else "N/A"
        )

        return result

    def generate_test_suite(
        self,
        task: str,
        source_code: str = "",
        filename: str = "",
        thread_id: str = "global",
    ) -> dict[str, Any]:
        """Full test generation pipeline: analyze → generate → report."""
        message_bus.send_message(
            sender=self.name,
            recipient="supervisor",
            content=f"Generating tests for {filename or 'provided code'}",
            summary="Testing agent started test generation",
            thread_id=thread_id,
        )

        result = self.analyze_code(source_code=source_code, filename=filename)

        message_bus.send_message(
            sender=self.name,
            recipient="supervisor",
            content=f"Generated {result.get('tests_generated', 0)} tests",
            summary="Testing agent completed",
            thread_id=thread_id,
        )

        return {
            "task": task,
            "agent": self.name,
            "status": "completed" if result.get("test_code") else "failed",
            **result,
        }

    def run_tests_or_generate(
        self,
        task: str,
        code: str = "",
        filename: str = "",
        thread_id: str = "global",
    ) -> dict[str, Any]:
        """Entry point for testing tasks from supervisor or swarm."""
        source = code
        if not source and filename:
            try:
                from src.tools.file_tools import read_workspace_file
                file_res = read_workspace_file(path=filename)
                source = file_res.get("content", "")
            except Exception:
                pass

        suite_res = self.generate_test_suite(
            task=task,
            source_code=source,
            filename=filename,
            thread_id=thread_id,
        )
        return {
            "status": "completed",
            "task": task,
            "filename": filename,
            "test_suite": suite_res.get("test_code", ""),
            "details": suite_res,
        }


testing_agent = TestingAgent()



@tool
def run_test_generation(
    source_code: str,
    filename: str = "",
    thread_id: str = "global",
) -> dict[str, Any]:
    """Analyze Python code and generate a comprehensive pytest test suite.

    Args:
        source_code: The Python source code to generate tests for.
        filename: Original filename for import path generation.
        thread_id: Context conversation thread ID.
    """
    return testing_agent.generate_test_suite(
        task="generate_tests",
        source_code=source_code,
        filename=filename,
        thread_id=thread_id,
    )
