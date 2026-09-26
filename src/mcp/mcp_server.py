"""Model Context Protocol (MCP) Server.

Exposes Agent-Pilot tools over the standard MCP JSON-RPC 2.0 protocol
for interoperability with Claude Code, Cursor, Antigravity, and external clients.
"""
from __future__ import annotations

import json
from typing import Any, Callable

# Map of tool names to their underlying LangChain tools or callables
_REGISTERED_TOOLS: dict[str, Any] = {}


def register_tool(name: str, tool_instance: Any) -> None:
    """Register a tool instance for MCP exposure."""
    _REGISTERED_TOOLS[name] = tool_instance


class MCPServer:
    """Handles MCP JSON-RPC 2.0 protocol requests."""

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_INFO = {"name": "agent-pilot-mcp", "version": "1.0.0"}

    def __init__(self, tools_dict: dict[str, Any] | None = None):
        self.tools = tools_dict if tools_dict is not None else _REGISTERED_TOOLS

    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP tool descriptors with JSON Schema input specs."""
        descriptors = []
        for name, tool_obj in self.tools.items():
            desc = getattr(tool_obj, "description", "") or f"Tool: {name}"
            # Extract or synthesize inputSchema
            args_schema = getattr(tool_obj, "args_schema", None)
            if args_schema and hasattr(args_schema, "model_json_schema"):
                input_schema = args_schema.model_json_schema()
            elif args_schema and hasattr(args_schema, "schema"):
                input_schema = args_schema.schema()
            else:
                input_schema = {"type": "object", "properties": {}}

            descriptors.append({
                "name": name,
                "description": desc.strip(),
                "inputSchema": input_schema,
            })
        return descriptors

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool and format the response as an MCP result block."""
        if name not in self.tools:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Tool '{name}' not found."}],
            }

        tool_obj = self.tools[name]
        try:
            if hasattr(tool_obj, "invoke"):
                result = tool_obj.invoke(arguments)
            elif callable(tool_obj):
                result = tool_obj(**arguments)
            else:
                result = str(tool_obj)

            text_output = json.dumps(result, default=str) if isinstance(result, (dict, list)) else str(result)
            return {
                "isError": False,
                "content": [{"type": "text", "text": text_output}],
            }
        except Exception as exc:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Tool execution failed: {exc}"}],
            }

    def handle_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """Process a JSON-RPC 2.0 MCP request."""
        req_id = request_data.get("id")
        method = request_data.get("method")
        params = request_data.get("params", {})

        if not method:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32600, "message": "Invalid Request: missing method"},
            }

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": self.SERVER_INFO,
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.list_tools()},
            }

        if method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            result = self.call_tool(tool_name, tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result,
            }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"},
        }


def load_default_tools() -> None:
    """Populate default Agent-Pilot tools into the MCP server."""
    try:
        from src.tools import web_search, scrape_web, read_workspace_file, write_workspace_file, query_database, call_api
        from src.memory import store_memory, retrieve_memory
        from src.agent import create_plan, reflect_on_goal
        from src.agents import route_to_specialist
        register_tool("web_search", web_search)
        register_tool("scrape_web", scrape_web)
        register_tool("read_workspace_file", read_workspace_file)
        register_tool("write_workspace_file", write_workspace_file)
        register_tool("query_database", query_database)
        register_tool("call_api", call_api)
        register_tool("store_memory", store_memory)
        register_tool("retrieve_memory", retrieve_memory)
        register_tool("create_plan", create_plan)
        register_tool("reflect_on_goal", reflect_on_goal)
        register_tool("route_to_specialist", route_to_specialist)
    except Exception:
        pass


# Default shared server instance
mcp_server = MCPServer()
load_default_tools()
