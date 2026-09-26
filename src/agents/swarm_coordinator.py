"""Swarm Coordinator for multi-agent orchestration.

Manages agent pools with configurable topologies (mesh, hierarchical, pipeline,
fan-out), supports parallel agent execution, dynamic work distribution, and
result aggregation across multiple specialist agents.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from langchain_core.tools import tool

from src.agents.shared_state import AgentRole, message_bus


class SwarmTopology(str, Enum):
    """Supported swarm coordination topologies."""
    HIERARCHICAL = "hierarchical"
    MESH = "mesh"
    PIPELINE = "pipeline"
    FAN_OUT = "fan-out"


class SwarmStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class AgentTask:
    """A unit of work assigned to an agent within a swarm."""
    agent_role: str = "general"
    description: str = ""
    task_input: str = ""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: str = "pending"
    result: Any = None
    error: str = ""
    duration_ms: float = 0.0
    depends_on: list[str] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""

    def __post_init__(self):
        if not self.description and self.task_input:
            self.description = self.task_input
        if isinstance(self.agent_role, AgentRole):
            self.agent_role = self.agent_role.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)



@dataclass
class SwarmSession:
    """Tracks a complete swarm execution session."""
    swarm_id: str
    topology: str
    goal: str
    tasks: list[AgentTask]
    status: str = "pending"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str = ""
    total_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tasks"] = [t.to_dict() for t in self.tasks]
        return d


class SwarmCoordinator:
    """Orchestrates multi-agent swarms with configurable topologies."""

    def __init__(self, max_parallel: int = 4, max_workers: Optional[int] = None):
        self.max_parallel = max_workers if max_workers is not None else max_parallel
        self._sessions: dict[str, SwarmSession] = {}
        self._agent_handlers: dict[str, Callable] = {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register built-in handlers for known agent roles."""
        def handle_research(desc: str, ctx: dict[str, Any]) -> Any:
            from src.agents.research_agent import research_agent
            return research_agent.research(topic=desc, thread_id=ctx.get("thread_id", "global"))

        def handle_coding(desc: str, ctx: dict[str, Any]) -> Any:
            from src.agents.coding_agent import coding_agent
            return coding_agent.execute_task(task=desc, thread_id=ctx.get("thread_id", "global"))

        def handle_data(desc: str, ctx: dict[str, Any]) -> Any:
            from src.agents.data_agent import data_analyst_agent
            return data_analyst_agent.analyze(task=desc, thread_id=ctx.get("thread_id", "global"))

        def handle_testing(desc: str, ctx: dict[str, Any]) -> Any:
            from src.agents.testing_agent import testing_agent
            return testing_agent.run_tests_or_generate(task=desc, thread_id=ctx.get("thread_id", "global"))

        def handle_general(desc: str, ctx: dict[str, Any]) -> Any:
            return {"status": "completed", "response": f"Processed: {desc}"}

        self.register_agent(AgentRole.RESEARCHER.value, handle_research)
        self.register_agent(AgentRole.CODER.value, handle_coding)
        self.register_agent(AgentRole.DATA_ANALYST.value, handle_data)
        self.register_agent(AgentRole.TESTING.value, handle_testing)
        self.register_agent(AgentRole.GENERAL.value, handle_general)
        self.register_agent("general", handle_general)
        self.register_agent("researcher", handle_research)
        self.register_agent("coder", handle_coding)
        self.register_agent("data-analyst", handle_data)
        self.register_agent("testing", handle_testing)

    def register_agent(self, role: str, handler: Callable) -> None:
        """Register an agent handler function for a given role."""
        self._agent_handlers[role] = handler

    def execute_swarm(
        self,
        topology: SwarmTopology | str,
        tasks: list[AgentTask],
        goal: str = "Swarm Goal",
        thread_id: str = "global",
    ) -> dict[str, Any]:
        """Execute a list of AgentTasks directly with the given topology."""
        swarm_id = str(uuid.uuid4())[:8]
        topo_str = topology.value if isinstance(topology, SwarmTopology) else str(topology)
        session = SwarmSession(
            swarm_id=swarm_id,
            topology=topo_str,
            goal=goal,
            tasks=tasks,
        )
        self._sessions[swarm_id] = session
        context = {"thread_id": thread_id, "goal": goal, "swarm_id": swarm_id}

        if topo_str in (SwarmTopology.FAN_OUT.value, SwarmTopology.MESH.value):
            self.run_fan_out(session, context)
        elif topo_str == SwarmTopology.PIPELINE.value:
            self.run_pipeline(session, context)
        elif topo_str == SwarmTopology.HIERARCHICAL.value:
            self.run_hierarchical(session, context)
        else:
            self.run_fan_out(session, context)

        completed_count = sum(1 for t in session.tasks if t.status == "completed")
        return {
            "swarm_id": swarm_id,
            "status": session.status,
            "topology": topo_str,
            "completed_tasks": completed_count,
            "total_tasks": len(session.tasks),
            "duration_ms": session.total_duration_ms,
            "tasks": [t.to_dict() for t in session.tasks],
        }


    def _execute_task(
        self, task: AgentTask, context: dict[str, Any]
    ) -> AgentTask:
        """Execute a single agent task and capture timing and results."""
        task.status = "running"
        task.started_at = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()

        handler = self._agent_handlers.get(task.agent_role)
        if not handler:
            task.status = "failed"
            task.error = f"No handler registered for role: {task.agent_role}"
            task.duration_ms = round((time.monotonic() - start) * 1000, 2)
            task.completed_at = datetime.now(timezone.utc).isoformat()
            return task

        try:
            result = handler(task.description, context)
            task.result = result
            task.status = "completed"
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)[:500]

        task.duration_ms = round((time.monotonic() - start) * 1000, 2)
        task.completed_at = datetime.now(timezone.utc).isoformat()

        message_bus.send_message(
            sender=task.agent_role,
            recipient="swarm_coordinator",
            content=f"Task {task.task_id} {task.status}",
            summary=f"{task.agent_role} finished: {task.status}",
            thread_id=context.get("thread_id", "global"),
        )
        return task

    def run_fan_out(
        self, session: SwarmSession, context: dict[str, Any]
    ) -> SwarmSession:
        """Execute all tasks in parallel and aggregate results."""
        session.status = "running"
        start = time.monotonic()

        with ThreadPoolExecutor(max_workers=self.max_parallel) as pool:
            futures = {
                pool.submit(self._execute_task, task, context): task
                for task in session.tasks
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass

        session.total_duration_ms = round((time.monotonic() - start) * 1000, 2)
        completed = sum(1 for t in session.tasks if t.status == "completed")
        if completed == len(session.tasks):
            session.status = "completed"
        elif completed > 0:
            session.status = "partial"
        else:
            session.status = "failed"
        session.completed_at = datetime.now(timezone.utc).isoformat()
        return session

    def run_pipeline(
        self, session: SwarmSession, context: dict[str, Any]
    ) -> SwarmSession:
        """Execute tasks sequentially, piping each result to the next."""
        session.status = "running"
        start = time.monotonic()
        pipeline_context = dict(context)

        for task in session.tasks:
            self._execute_task(task, pipeline_context)
            if task.status == "failed":
                session.status = "partial"
                break
            pipeline_context["previous_result"] = task.result

        session.total_duration_ms = round((time.monotonic() - start) * 1000, 2)
        if all(t.status == "completed" for t in session.tasks):
            session.status = "completed"
        session.completed_at = datetime.now(timezone.utc).isoformat()
        return session

    def run_hierarchical(
        self, session: SwarmSession, context: dict[str, Any]
    ) -> SwarmSession:
        """Execute tasks respecting dependency ordering (topological sort)."""
        session.status = "running"
        start = time.monotonic()
        completed_ids: set[str] = set()
        task_map = {t.task_id: t for t in session.tasks}

        remaining = list(session.tasks)
        while remaining:
            ready = [
                t for t in remaining
                if all(dep in completed_ids for dep in t.depends_on)
            ]
            if not ready:
                for t in remaining:
                    t.status = "failed"
                    t.error = "Circular dependency or unresolvable dependency"
                break

            with ThreadPoolExecutor(max_workers=self.max_parallel) as pool:
                futures = {
                    pool.submit(self._execute_task, t, context): t for t in ready
                }
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        pass

            for t in ready:
                if t.status == "completed":
                    completed_ids.add(t.task_id)
                remaining.remove(t)

        session.total_duration_ms = round((time.monotonic() - start) * 1000, 2)
        completed = sum(1 for t in session.tasks if t.status == "completed")
        if completed == len(session.tasks):
            session.status = "completed"
        elif completed > 0:
            session.status = "partial"
        else:
            session.status = "failed"
        session.completed_at = datetime.now(timezone.utc).isoformat()
        return session

    def create_swarm(
        self,
        goal: str,
        agent_tasks: list[dict[str, Any]],
        topology: str = "fan-out",
        thread_id: str = "global",
    ) -> SwarmSession:
        """Create and execute a swarm of agent tasks."""
        swarm_id = str(uuid.uuid4())[:8]
        tasks = []
        for i, at in enumerate(agent_tasks):
            tasks.append(AgentTask(
                task_id=at.get("task_id", f"task-{i+1}"),
                agent_role=at.get("role", "general"),
                description=at.get("description", ""),
                depends_on=at.get("depends_on", []),
            ))

        session = SwarmSession(
            swarm_id=swarm_id,
            topology=topology,
            goal=goal,
            tasks=tasks,
        )
        self._sessions[swarm_id] = session

        context = {"thread_id": thread_id, "goal": goal, "swarm_id": swarm_id}

        topo = SwarmTopology(topology) if topology in [t.value for t in SwarmTopology] else SwarmTopology.FAN_OUT
        if topo == SwarmTopology.FAN_OUT or topo == SwarmTopology.MESH:
            self.run_fan_out(session, context)
        elif topo == SwarmTopology.PIPELINE:
            self.run_pipeline(session, context)
        elif topo == SwarmTopology.HIERARCHICAL:
            self.run_hierarchical(session, context)

        return session

    def get_session(self, swarm_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a swarm session by ID."""
        session = self._sessions.get(swarm_id)
        return session.to_dict() if session else None


swarm_coordinator = SwarmCoordinator()


@tool
def create_agent_swarm(
    goal: str,
    agent_tasks: list[dict[str, Any]],
    topology: str = "fan-out",
    thread_id: str = "global",
) -> dict[str, Any]:
    """Launch a coordinated swarm of agents working on a shared goal.

    Args:
        goal: The overarching objective for the swarm.
        agent_tasks: List of dicts with 'role', 'description', and optional 'depends_on' keys.
        topology: Coordination pattern — 'fan-out', 'pipeline', 'hierarchical', or 'mesh'.
        thread_id: Context thread identifier.
    """
    if not goal.strip():
        return {"error": "Swarm goal cannot be empty."}
    if not agent_tasks:
        return {"error": "At least one agent task is required."}
    session = swarm_coordinator.create_swarm(
        goal=goal, agent_tasks=agent_tasks, topology=topology, thread_id=thread_id
    )
    return session.to_dict()
