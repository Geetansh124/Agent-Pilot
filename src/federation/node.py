"""Federation protocol and multi-node agent network registry.

Enables secure inter-node communication, remote agent pool discovery,
authenticated message envelopes, and distributed task dispatching across nodes.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional


@dataclass
class FederatedNode:
    node_id: str
    endpoint_url: str
    available_agents: list[str] = field(default_factory=list)
    status: str = "online"  # online, offline, busy
    last_heartbeat: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FederatedMessageEnvelope:
    message_id: str
    source_node: str
    target_node: str
    recipient_agent: str
    payload: dict[str, Any]
    signature: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FederationNetwork:
    """Manages multi-node discovery, message signing, and remote routing."""

    def __init__(self, local_node_id: str = "node-local", secret_key: str = "federation-secret"):
        self.local_node_id = local_node_id
        self.secret_key = secret_key
        self._nodes: dict[str, FederatedNode] = {}
        self._inbox: list[FederatedMessageEnvelope] = []
        self._register_local_node()

    def _register_local_node(self) -> None:
        self.register_node(
            node_id=self.local_node_id,
            endpoint_url="http://localhost:8000",
            available_agents=["supervisor", "researcher", "coder", "data-analyst", "testing"],
        )

    def register_node(
        self,
        node_id: str,
        endpoint_url: str,
        available_agents: list[str],
        metadata: Optional[dict[str, Any]] = None,
    ) -> FederatedNode:
        """Register or update a remote node in the federation registry."""
        node = FederatedNode(
            node_id=node_id,
            endpoint_url=endpoint_url,
            available_agents=available_agents,
            status="online",
            last_heartbeat=time.time(),
            metadata=metadata or {},
        )
        self._nodes[node_id] = node
        return node

    def sign_message(self, message_id: str, payload: dict[str, Any]) -> str:
        """Generate HMAC-SHA256 signature for message envelope integrity."""
        raw = f"{message_id}:{json.dumps(payload, sort_keys=True)}"
        return hmac.new(
            self.secret_key.encode("utf-8"),
            raw.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_signature(self, envelope: FederatedMessageEnvelope) -> bool:
        """Verify HMAC-SHA256 signature on an incoming envelope."""
        expected = self.sign_message(envelope.message_id, envelope.payload)
        return hmac.compare_digest(envelope.signature, expected)

    def create_envelope(
        self,
        target_node: str,
        recipient_agent: str,
        payload: dict[str, Any],
    ) -> FederatedMessageEnvelope:
        """Construct and sign a federated message envelope."""
        msg_id = str(uuid.uuid4())[:12]
        signature = self.sign_message(msg_id, payload)
        return FederatedMessageEnvelope(
            message_id=msg_id,
            source_node=self.local_node_id,
            target_node=target_node,
            recipient_agent=recipient_agent,
            payload=payload,
            signature=signature,
        )

    def route_federated_task(
        self, agent_role: str, task: str, context: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Find a capable node hosting the requested agent role and construct envelope."""
        capable_nodes = [
            n for n in self._nodes.values()
            if agent_role in n.available_agents and n.status == "online"
        ]

        if not capable_nodes:
            return {
                "status": "error",
                "error": f"No online federation node provides agent: {agent_role}",
            }

        target = capable_nodes[0]
        envelope = self.create_envelope(
            target_node=target.node_id,
            recipient_agent=agent_role,
            payload={"task": task, "context": context or {}},
        )

        # If targeting local node, dispatch locally
        if target.node_id == self.local_node_id:
            from src.agents.supervisor import supervisor_agent
            res = supervisor_agent.delegate(task=task, role=agent_role)
            return {
                "status": "completed",
                "dispatched_to": target.node_id,
                "envelope_id": envelope.message_id,
                "result": res,
            }

        return {
            "status": "forwarded",
            "dispatched_to": target.node_id,
            "target_endpoint": target.endpoint_url,
            "envelope": envelope.to_dict(),
        }

    def list_nodes(self) -> list[dict[str, Any]]:
        """List all active nodes and their agent capabilities."""
        return [n.to_dict() for n in self._nodes.values()]


federation_network = FederationNetwork()
