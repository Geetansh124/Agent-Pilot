"""Autonomous planning, reflection, and goal completion detection (ReAct framework).

Enables multi-step tool problem solving with explicit planning,
step execution tracking, observation reflection, and goal completion assessment.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional
from langchain_core.tools import tool


class PlanState:
    """In-memory active execution plan tracking."""

    def __init__(self):
        self._plans: dict[str, dict[str, Any]] = {}

    def create(self, goal: str, steps: list[str], plan_id: Optional[str] = None) -> dict[str, Any]:
        pid = plan_id or str(uuid.uuid4())[:8]
        clean_steps = [
            {"step": i + 1, "description": s.strip(), "status": "pending", "result": ""}
            for i, s in enumerate(steps)
            if s.strip()
        ]
        plan = {
            "plan_id": pid,
            "goal": goal.strip(),
            "steps": clean_steps,
            "total_steps": len(clean_steps),
            "completed_steps": 0,
            "status": "in_progress",
        }
        self._plans[pid] = plan
        return plan

    def update_step(
        self, plan_id: str, step_number: int, status: str, result: str = ""
    ) -> dict[str, Any]:
        if plan_id not in self._plans:
            return {"error": f"Plan '{plan_id}' not found.", "status": "failed"}

        plan = self._plans[plan_id]
        clean_status = status.lower().strip()
        for step in plan["steps"]:
            if step["step"] == step_number:
                step["status"] = clean_status
                if result:
                    step["result"] = result[:1000]
                break

        completed = sum(1 for s in plan["steps"] if s["status"] in ("completed", "done"))
        plan["completed_steps"] = completed
        if completed == plan["total_steps"] and plan["total_steps"] > 0:
            plan["status"] = "completed"

        return plan

    def get_plan(self, plan_id: str) -> Optional[dict[str, Any]]:
        return self._plans.get(plan_id)


_plan_state = PlanState()


@tool
def create_plan(goal: str, steps: list[str]) -> dict[str, Any]:
    """Create a structured multi-step execution plan for complex tasks.

    Args:
        goal: The overarching objective or user question.
        steps: List of sequential step descriptions (e.g. ['Search web for latest specs', 'Analyze benchmark data']).
    """
    if not goal.strip():
        return {"error": "Plan goal cannot be empty."}
    if not steps:
        return {"error": "Plan must contain at least one step."}
    return _plan_state.create(goal=goal, steps=steps)


@tool
def update_plan_step(
    plan_id: str, step_number: int, status: str, result_summary: str = ""
) -> dict[str, Any]:
    """Update progress on a specific step in an active plan.

    Args:
        plan_id: The ID of the active plan.
        step_number: 1-indexed step number to update.
        status: New status ('in_progress', 'completed', 'blocked', 'skipped').
        result_summary: Brief note or tool output summary for this step.
    """
    return _plan_state.update_step(
        plan_id=plan_id,
        step_number=step_number,
        status=status,
        result=result_summary,
    )


@tool
def reflect_on_goal(
    goal: str, observations: list[str], completed_steps: list[str]
) -> dict[str, Any]:
    """Evaluate whether the user's goal has been accomplished or requires further action.

    Args:
        goal: The target objective.
        observations: Insights collected from recent tool invocations.
        completed_steps: Names or descriptions of steps executed so far.
    """
    clean_goal = goal.strip()
    obs_count = len(observations)
    steps_count = len(completed_steps)

    has_meaningful_data = any(len(o.strip()) > 20 for o in observations)

    if steps_count > 0 and has_meaningful_data:
        goal_completed = True
        next_action = "Formulate comprehensive, cited final answer for the user."
        reflection = f"Collected {obs_count} observations across {steps_count} completed steps; sufficient to answer goal."
    else:
        goal_completed = False
        next_action = "Execute next planned research, calculation, or analysis tool."
        reflection = f"Only {steps_count} steps executed and need more evidence to answer '{clean_goal[:60]}'."

    return {
        "goal": clean_goal,
        "goal_completed": goal_completed,
        "next_action": next_action,
        "reflection": reflection,
        "observations_analyzed": obs_count,
    }
