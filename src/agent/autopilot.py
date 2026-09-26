"""Autopilot Engine for autonomous multi-step goal execution.

Executes continuous Observe-Plan-Act-Reflect cycles to autonomously drive
complex goals to completion with iteration limits, safety boundaries,
and status reflection.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from langchain_core.tools import tool


class AutopilotStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"


@dataclass
class AutopilotStep:
    step_id: str
    description: str
    action_type: str
    status: str = "pending"  # pending, running, completed, failed
    result: Any = None
    reflection: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AutopilotMission:
    mission_id: str
    goal: str
    status: AutopilotStatus = AutopilotStatus.IDLE
    steps: list[AutopilotStep] = field(default_factory=list)
    current_step_idx: int = 0
    max_iterations: int = 10
    iterations_run: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["steps"] = [s.to_dict() for s in self.steps]
        return d


class AutopilotEngine:
    """Autonomous goal runner driving missions through iterative execution and reflection."""

    def __init__(self, step_executor: Optional[Callable] = None):
        self._missions: dict[str, AutopilotMission] = {}
        self.step_executor = step_executor or self._default_executor

    def _default_executor(self, step_desc: str, context: dict[str, Any]) -> Any:
        """Default step execution delegating to supervisor agent."""
        from src.agents.supervisor import supervisor_agent
        return supervisor_agent.delegate(
            task=step_desc,
            thread_id=context.get("thread_id", "autopilot"),
        )

    def plan_mission(
        self, goal: str, max_iterations: int = 8, thread_id: str = "autopilot"
    ) -> AutopilotMission:
        """Decompose a high-level goal into actionable autopilot steps."""
        mission_id = str(uuid.uuid4())[:8]

        # Simple goal decomposition heuristics
        steps = [
            AutopilotStep(
                step_id=f"{mission_id}-1",
                description=f"Research and gather context for: {goal}",
                action_type="research",
            ),
            AutopilotStep(
                step_id=f"{mission_id}-2",
                description=f"Execute core actions and generate artifacts for: {goal}",
                action_type="execution",
            ),
            AutopilotStep(
                step_id=f"{mission_id}-3",
                description=f"Validate, test, and review outcomes for: {goal}",
                action_type="validation",
            ),
        ]

        mission = AutopilotMission(
            mission_id=mission_id,
            goal=goal,
            status=AutopilotStatus.PLANNING,
            steps=steps,
            max_iterations=max_iterations,
        )
        self._missions[mission_id] = mission
        return mission

    def run_mission(
        self, goal: str, max_iterations: int = 8, thread_id: str = "autopilot"
    ) -> dict[str, Any]:
        """Execute a full autonomous mission from planning to completion."""
        mission = self.plan_mission(goal=goal, max_iterations=max_iterations, thread_id=thread_id)
        mission.status = AutopilotStatus.EXECUTING
        context = {"thread_id": thread_id, "mission_id": mission.mission_id, "goal": goal}

        for idx, step in enumerate(mission.steps):
            if mission.iterations_run >= mission.max_iterations:
                mission.status = AutopilotStatus.PAUSED
                break

            mission.current_step_idx = idx
            step.status = "running"
            start = time.monotonic()

            try:
                result = self.step_executor(step.description, context)
                step.result = result
                step.status = "completed"
                step.reflection = f"Step succeeded: generated {len(str(result))} characters of output."
            except Exception as exc:
                step.status = "failed"
                step.result = str(exc)
                step.reflection = f"Step failed with error: {exc}"
                mission.status = AutopilotStatus.FAILED
                break
            finally:
                step.duration_ms = round((time.monotonic() - start) * 1000, 2)
                mission.iterations_run += 1

        if mission.status == AutopilotStatus.EXECUTING:
            mission.status = AutopilotStatus.COMPLETED
            mission.summary = f"All {len(mission.steps)} mission steps completed successfully."
            mission.completed_at = datetime.now(timezone.utc).isoformat()

        return mission.to_dict()

    def get_mission_status(self, mission_id: str) -> Optional[dict[str, Any]]:
        """Query state and steps of an active or past mission."""
        mission = self._missions.get(mission_id)
        return mission.to_dict() if mission else None


autopilot_engine = AutopilotEngine()


@tool
def run_autopilot_mission(
    goal: str, max_iterations: int = 8, thread_id: str = "autopilot"
) -> dict[str, Any]:
    """Launch an autonomous autopilot mission that observes, plans, executes, and validates a goal.

    Args:
        goal: The objective to achieve.
        max_iterations: Maximum allowed execution steps before stopping.
        thread_id: Context thread ID.
    """
    if not goal.strip():
        return {"error": "Mission goal cannot be empty."}
    return autopilot_engine.run_mission(
        goal=goal, max_iterations=max_iterations, thread_id=thread_id
    )
