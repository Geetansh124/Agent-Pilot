"""Model Context Protocol (MCP) Client.

Enables Agent-Pilot to connect to external MCP servers, discover remote tools,
and adapt them into LangChain callables for the agent graph.
"""
from __future__ import annotations

import json
from typing import Any, Optional
import requests
from langchain_core.tools import StructuredTool, tool


class MCPClient:
    """Client for external Model Context Protocol JSON-RPC servers."""

    def __init__(self, endpoint_url: str, timeout_seconds: float = 10.0):
        self.endpoint_url = endpoint_url
        self.timeout = timeout_seconds
        self._request_counter = 0

    def _rpc_call(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self._request_counter += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_counter,
            "method": method,
            "params": params or {},
        }
        try:
            resp = requests.post(self.endpoint_url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"MCP RPC Error: {data['error'].get('message', 'Unknown error')}")
            return data.get("result", {})
        except Exception as exc:
            raise RuntimeError(f"Failed to communicate with MCP server at {self.endpoint_url}: {exc}") from exc

    def list_remote_tools(self) -> list[dict[str, Any]]:
        """Fetch remote tools declared by the external MCP server."""
        res = self._rpc_call("tools/list")
        return res.get("tools", [])

    def call_remote_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a remote tool over MCP JSON-RPC."""
        return self._rpc_call("tools/call", {"name": name, "arguments": arguments})

    def create_langchain_tools(self) -> list[Any]:
        """Convert discovered remote tools into LangChain tool instances."""
        remote_tools = self.list_remote_tools()
        lc_tools = []

        for t in remote_tools:
            tool_name = t.get("name", "remote_tool")
            description = t.get("description", f"External MCP tool: {tool_name}")

            def _make_invoker(t_name: str):
                def _invoke(**kwargs: Any) -> Any:
                    return self.call_remote_tool(t_name, kwargs)
                return _invoke

            wrapped = StructuredTool.from_function(
                func=_make_invoker(tool_name),
                name=f"mcp_{tool_name}",
                description=description,
            )
            lc_tools.append(wrapped)

        return lc_tools
