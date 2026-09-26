"""Task scheduling and automation engine.

Provides cron/interval-based task scheduling for recurring jobs such as
automated research, health monitoring, data synchronization, and reporting.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from langchain_core.tools import tool


@dataclass
class ScheduledTask:
    task_id: str
    name: str
    interval_seconds: int
    action_payload: dict[str, Any]
    next_run_timestamp: float
    status: str = "active"  # active, paused, cancelled
    run_count: int = 0
    last_run_result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskScheduler:
    """Manages scheduled background automation tasks."""

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}

    def schedule(
        self,
        name: str,
        interval_seconds: int,
        action_payload: Optional[dict[str, Any]] = None,
    ) -> ScheduledTask:
        """Register a new interval-based scheduled task."""
        tid = str(uuid.uuid4())[:8]
        now = time.time()
        task = ScheduledTask(
            task_id=tid,
            name=name.strip(),
            interval_seconds=max(5, interval_seconds),
            action_payload=action_payload or {},
            next_run_timestamp=now + interval_seconds,
        )
        self._tasks[tid] = task
        return task

    def cancel(self, task_id: str) -> bool:
        """Cancel a scheduled task."""
        task = self._tasks.get(task_id)
        if task and task.status != "cancelled":
            task.status = "cancelled"
            return True
        return False

    def list_tasks(self, include_cancelled: bool = False) -> list[dict[str, Any]]:
        """List active scheduled tasks."""
        return [
            t.to_dict()
            for t in self._tasks.values()
            if include_cancelled or t.status == "active"
        ]

    def get_due_tasks(self) -> list[ScheduledTask]:
        """Fetch all tasks whose scheduled run time has arrived."""
        now = time.time()
        due = [
            t
            for t in self._tasks.values()
            if t.status == "active" and t.next_run_timestamp <= now
        ]
        return due

    def mark_executed(self, task_id: str, result_summary: str = "Success") -> None:
        """Record task execution and compute next run timestamp."""
        task = self._tasks.get(task_id)
        if task:
            task.run_count += 1
            task.last_run_result = result_summary[:500]
            task.next_run_timestamp = time.time() + task.interval_seconds


task_scheduler = TaskScheduler()


@tool
def schedule_recurring_task(
    task_name: str, interval_seconds: int, action_description: str
) -> dict[str, Any]:
    """Schedule a recurring automated task (e.g. daily report, price check, document sync).

    Args:
        task_name: Human-readable name for the recurring job.
        interval_seconds: Execution frequency in seconds (e.g. 3600 for hourly, 86400 for daily).
        action_description: Description of the action or tool sequence to execute.
    """
    task = task_scheduler.schedule(
        name=task_name,
        interval_seconds=interval_seconds,
        action_payload={"description": action_description},
    )
    return {
        "task_id": task.task_id,
        "name": task.name,
        "interval_seconds": task.interval_seconds,
        "status": task.status,
    }
