"""Shared state and inter-agent communication protocol.

Provides structured message passing between specialized agents
(researcher, coder, data-analyst, supervisor) following SendMessage-first coordination.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class AgentRole(str, Enum):
    SUPERVISOR = "supervisor"
    RESEARCHER = "researcher"
    CODER = "coder"
    DATA_ANALYST = "data-analyst"
    GENERAL = "general"


@dataclass
class AgentMessage:
    """A direct message passed between named agents."""

    sender: str
    recipient: str
    content: str
    summary: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InterAgentMessageBus:
    """In-memory communication bus for agent-to-agent coordination."""

    def __init__(self):
        self._history: dict[str, list[AgentMessage]] = {}

    def send_message(
        self,
        sender: str,
        recipient: str,
        content: str,
        summary: str = "",
        thread_id: str = "global",
        artifacts: Optional[list[dict[str, Any]]] = None,
    ) -> AgentMessage:
        """Post a direct message from one agent to another within a thread context."""
        msg = AgentMessage(
            sender=sender,
            recipient=recipient,
            content=content.strip(),
            summary=summary.strip() or f"Message from {sender} to {recipient}",
            artifacts=artifacts or [],
        )
        if thread_id not in self._history:
            self._history[thread_id] = []
        self._history[thread_id].append(msg)
        return msg

    def get_messages(
        self, thread_id: str = "global", recipient: Optional[str] = None
    ) -> list[AgentMessage]:
        """Fetch all messages directed to a recipient in a thread."""
        msgs = self._history.get(thread_id, [])
        if recipient:
            return [m for m in msgs if m.recipient == recipient]
        return list(msgs)

    def clear(self, thread_id: str = "global") -> None:
        """Clear message history for a thread."""
        self._history.pop(thread_id, None)


message_bus = InterAgentMessageBus()
