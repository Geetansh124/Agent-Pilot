"""Model Context Protocol (MCP) Server.

Exposes Agent-Pilot tools over the standard MCP JSON-RPC 2.0 protocol
with constant-time bearer authentication and server-side tenant scoping.
"""
from __future__ import annotations

import hmac
import inspect
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

# Map of tool names to their underlying tools or callables
_REGISTERED_TOOLS: dict[str, Any] = {}


def _filter_callable_args(fn: Callable[..., Any], args: dict[str, Any]) -> dict[str, Any]:
    """Filter arguments to only those accepted by the target callable."""
    try:
        sig = inspect.signature(fn)
        has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        if has_varkw:
            return args
        accepted = set(sig.parameters.keys())
        return {k: v for k, v in args.items() if k in accepted}
    except Exception:
        return args


def verify_bearer_token(auth_header: Optional[str], expected_token: Optional[str] = None) -> bool:
    """Verify authorization header using constant-time comparison."""
    if not auth_header:
        return False
    parts = auth_header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    token = parts[1]
    if expected_token is None:
        expected_token = os.getenv("MCP_INTERNAL_TOKEN", "ap-internal-mcp-bearer-token")
    return hmac.compare_digest(token.encode("utf-8"), expected_token.encode("utf-8"))


def register_tool(name: str, tool_instance: Any) -> None:
    """Register a tool instance for MCP exposure."""
    _REGISTERED_TOOLS[name] = tool_instance


def rag_tool(query: str, thread_id: str = "default", user_id: str = "guest") -> dict[str, Any]:
    """Retrieve document context, citations, and scores for the active thread."""
    try:
        from src.rag import multi_doc_manager
        docs = multi_doc_manager.get_documents(thread_id)
        if not docs:
            return {
                "has_document": False,
                "context": "No documents uploaded for this thread. Please upload a document to enable RAG analysis.",
                "citations": [],
                "scores": [],
            }
        retriever = multi_doc_manager.get_hybrid_retriever(thread_id)
        citations = []
        contexts = []
        scores = []
        if retriever:
            results = retriever.invoke(query)
            for r in results:
                contexts.append(getattr(r, "page_content", str(r)))
                meta = getattr(r, "metadata", {})
                citations.append({
                    "doc_id": meta.get("doc_id", "doc-01"),
                    "filename": meta.get("filename", "document"),
                    "score": meta.get("score", 1.0),
                })
                scores.append(meta.get("score", 1.0))
        return {
            "has_document": True,
            "context": "\n\n".join(contexts) if contexts else "Relevant document passages retrieved.",
            "citations": citations,
            "scores": scores,
        }
    except Exception as exc:
        return {
            "has_document": False,
            "context": f"RAG query error: {exc}",
            "citations": [],
            "scores": [],
        }


def get_current_datetime() -> dict[str, Any]:
    """Return current server UTC datetime and epoch timestamp."""
    return {
        "iso": datetime.now(timezone.utc).isoformat(),
        "timestamp": time.time(),
    }


class MCPServer:
    """Handles MCP JSON-RPC 2.0 protocol requests with security policies."""

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_INFO = {"name": "agent-pilot-mcp", "version": "1.0.0"}

    def __init__(self, tools_dict: Optional[dict[str, Any]] = None):
        self.tools = tools_dict if tools_dict is not None else _REGISTERED_TOOLS

    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP tool descriptors with JSON Schema input specs."""
        descriptors = []
        for name, tool_obj in self.tools.items():
            desc = getattr(tool_obj, "description", "") or f"Tool: {name}"
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

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        tenant_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute a tool with server-side tenant scoping and HITL approval gating."""
        if name not in self.tools:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Tool '{name}' not found."}],
            }

        # Server-side tenant scoping: override model-supplied arguments
        if tenant_id:
            arguments["user_id"] = tenant_id
        if thread_id:
            arguments["thread_id"] = thread_id

        # Check HITL approval policy for sensitive tools
        from src.agent import hitl_manager
        if hitl_manager.is_sensitive(name) and not getattr(hitl_manager, "auto_approve", False):
            req = hitl_manager.request_approval(
                tool_name=name,
                arguments=arguments,
                thread_id=thread_id or "global",
            )
            if req.status != "approved":
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Tool '{name}' requires human authorization."}],
                    "requiresApproval": True,
                    "approvalId": req.request_id,
                }

        tool_obj = self.tools[name]
        try:
            if hasattr(tool_obj, "invoke"):
                result = tool_obj.invoke(arguments)
            elif callable(tool_obj):
                filtered_args = _filter_callable_args(tool_obj, arguments)
                result = tool_obj(**filtered_args)
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

    def handle_request(
        self,
        request_data: dict[str, Any],
        tenant_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> dict[str, Any]:
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
            result = self.call_tool(tool_name, tool_args, tenant_id=tenant_id, thread_id=thread_id)
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
    register_tool("rag_tool", rag_tool)
    register_tool("get_current_datetime", get_current_datetime)
    try:
        from src.tools import (
            web_search, scrape_web, read_workspace_file,
            write_workspace_file, delete_workspace_file,
            query_database, call_api,
        )
        from src.memory import store_memory, retrieve_memory
        register_tool("web_search", web_search)
        register_tool("scrape_web", scrape_web)
        register_tool("read_workspace_file", read_workspace_file)
        register_tool("write_workspace_file", write_workspace_file)
        register_tool("delete_workspace_file", delete_workspace_file)
        register_tool("query_database", query_database)
        register_tool("call_api", call_api)
        register_tool("store_memory", store_memory)
        register_tool("retrieve_memory", retrieve_memory)
    except Exception:
        pass


mcp_server = MCPServer()
load_default_tools()
