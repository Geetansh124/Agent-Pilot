"""Unit tests for Agent-Pilot MCP server, bearer authentication, and RAG parity."""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api_server import app
from src.mcp.mcp_server import MCPServer, get_current_datetime, rag_tool, verify_bearer_token


class TestHarnessMCPBridge(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.valid_token = "ap-internal-mcp-bearer-token"
        self.headers = {
            "Authorization": f"Bearer {self.valid_token}",
            "Content-Type": "application/json",
            "X-Tenant-ID": "user-tenant-01",
            "X-Thread-ID": "thread-mcp-01",
        }

    def test_verify_bearer_token_constant_time(self):
        self.assertTrue(verify_bearer_token(f"Bearer {self.valid_token}", self.valid_token))
        self.assertFalse(verify_bearer_token("Bearer wrong-token", self.valid_token))
        self.assertFalse(verify_bearer_token("Basic invalid", self.valid_token))
        self.assertFalse(verify_bearer_token(None, self.valid_token))

    def test_mcp_endpoint_rejects_unauthorized_requests(self):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        resp = self.client.post("/mcp", json=body)
        self.assertEqual(resp.status_code, 401)

        bad_resp = self.client.post(
            "/mcp",
            json=body,
            headers={"Authorization": "Bearer bad-token", "Content-Type": "application/json"},
        )
        self.assertEqual(bad_resp.status_code, 401)

    def test_mcp_initialize_and_tools_list(self):
        body_init = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        resp_init = self.client.post("/mcp", json=body_init, headers=self.headers)
        self.assertEqual(resp_init.status_code, 200)
        data_init = resp_init.json()
        self.assertEqual(data_init["result"]["serverInfo"]["name"], "agent-pilot-mcp")

        body_list = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        resp_list = self.client.post("/mcp", json=body_list, headers=self.headers)
        self.assertEqual(resp_list.status_code, 200)
        tools = [t["name"] for t in resp_list.json()["result"]["tools"]]
        self.assertIn("rag_tool", tools)
        self.assertIn("get_current_datetime", tools)

    def test_mcp_call_get_current_datetime(self):
        body_call = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_current_datetime", "arguments": {}},
        }
        resp = self.client.post("/mcp", json=body_call, headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        result = resp.json()["result"]
        self.assertFalse(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("iso", text)

    @patch("src.rag.multi_doc_manager.MultiDocManager.get_documents")
    @patch("src.rag.multi_doc_manager.MultiDocManager.get_hybrid_retriever")
    def test_rag_tool_returns_context_citations_and_scores(self, mock_get_retriever, mock_get_docs):
        mock_get_docs.return_value = [{"id": "doc-01", "filename": "spec.pdf"}]
        mock_doc = MagicMock()
        mock_doc.page_content = "Relevant architecture excerpt"
        mock_doc.metadata = {"doc_id": "doc-01", "filename": "spec.pdf", "score": 0.92}
        mock_retriever = MagicMock()
        mock_retriever.invoke.return_value = [mock_doc]
        mock_get_retriever.return_value = mock_retriever

        result = rag_tool("Tell me about architecture", thread_id="thread-mcp-01")
        self.assertTrue(result["has_document"])
        self.assertIn("Relevant architecture excerpt", result["context"])
        self.assertEqual(len(result["citations"]), 1)
        self.assertEqual(result["citations"][0]["doc_id"], "doc-01")
        self.assertEqual(result["scores"], [0.92])

    def test_rag_tool_reports_missing_document(self):
        with patch("src.rag.multi_doc_manager.MultiDocManager.get_documents", return_value=[]):
            result = rag_tool("Summarize doc", thread_id="empty-thread")
            self.assertFalse(result["has_document"])
            self.assertIn("Please upload a document", result["context"])


if __name__ == "__main__":
    unittest.main()

