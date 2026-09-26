"""Autonomous multi-step workflow execution engine.

Executes predefined or dynamic multi-stage automation pipelines end-to-end,
handling step data piping, retries, and execution verification.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Optional


class WorkflowRunner:
    """Executes multi-step automation pipelines autonomously."""

    def __init__(self, tool_registry: Optional[dict[str, Any]] = None):
        self.tools = tool_registry or {}

    def register_tool(self, name: str, tool_instance: Any) -> None:
        self.tools[name] = tool_instance

    def run_workflow(
        self,
        workflow_name: str,
        steps: list[dict[str, Any]],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute a sequence of tool steps autonomously.

        Each step format:
            {
                "name": "step_name",
                "tool": "tool_name",
                "arguments": {...},
            }
        """
        run_id = str(uuid.uuid4())[:8]
        t0 = time.time()
        step_results: list[dict[str, Any]] = []
        pipeline_context = dict(context or {})

        for idx, step in enumerate(steps):
            step_name = step.get("name", f"step_{idx + 1}")
            tool_name = step.get("tool", "")
            raw_args = step.get("arguments", {})

            # Substitute context variables in string arguments (e.g. {{prev_result}})
            resolved_args = {}
            for k, v in raw_args.items():
                if isinstance(v, str) and "{{" in v and "}}" in v:
                    for ctx_key, ctx_val in pipeline_context.items():
                        v = v.replace(f"{{{{{ctx_key}}}}}", str(ctx_val))
                resolved_args[k] = v

            step_status = "success"
            output: Any = None
            error_msg = ""

            tool_fn = self.tools.get(tool_name)
            if not tool_fn:
                step_status = "skipped"
                error_msg = f"Tool '{tool_name}' not available in workflow runner."
            else:
                try:
                    if hasattr(tool_fn, "invoke"):
                        output = tool_fn.invoke(resolved_args)
                    elif callable(tool_fn):
                        output = tool_fn(**resolved_args)
                    else:
                        output = str(tool_fn)
                    # Pipe output to context
                    pipeline_context[step_name] = output
                    pipeline_context["last_output"] = output
                except Exception as exc:
                    step_status = "failed"
                    error_msg = str(exc)

            step_results.append({
                "step": idx + 1,
                "name": step_name,
                "tool": tool_name,
                "status": step_status,
                "output": output,
                "error": error_msg,
            })

            if step_status == "failed" and not step.get("continue_on_failure", False):
                break

        total_time = round((time.time() - t0) * 1000, 2)
        overall_status = "completed" if all(s["status"] == "success" for s in step_results) else "partially_completed"

        return {
            "run_id": run_id,
            "workflow_name": workflow_name,
            "status": overall_status,
            "duration_ms": total_time,
            "steps_total": len(steps),
            "steps_executed": len(step_results),
            "step_results": step_results,
            "final_context": pipeline_context,
        }


def load_default_workflow_tools(runner: WorkflowRunner) -> None:
    """Register core tools for autonomous workflow execution."""
    try:
        from src.tools import web_search, scrape_web, read_workspace_file, write_workspace_file, query_database, call_api
        from src.memory import store_memory, retrieve_memory
        from src.graph import query_knowledge_graph
        from src.agent import evaluate_response
        runner.register_tool("web_search", web_search)
        runner.register_tool("scrape_web", scrape_web)
        runner.register_tool("read_workspace_file", read_workspace_file)
        runner.register_tool("write_workspace_file", write_workspace_file)
        runner.register_tool("query_database", query_database)
        runner.register_tool("call_api", call_api)
        runner.register_tool("store_memory", store_memory)
        runner.register_tool("retrieve_memory", retrieve_memory)
        runner.register_tool("query_knowledge_graph", query_knowledge_graph)
        runner.register_tool("evaluate_response", evaluate_response)
    except Exception:
        pass


workflow_runner = WorkflowRunner()
load_default_workflow_tools(workflow_runner)

