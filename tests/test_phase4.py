import unittest
from fastapi.testclient import TestClient

from api_server import app
from src.agents import (
    AgentRole,
    coding_agent,
    data_analyst_agent,
    message_bus,
    research_agent,
    route_to_specialist,
    run_code_task,
    run_data_analysis,
    run_research,
    supervisor_agent,
)
from src.mcp import MCPClient, MCPServer, mcp_server


class TestPhase4MultiAgentAndMCP(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        message_bus.clear("test-thread-p4")

    def test_inter_agent_message_bus(self):
        tid = "test-thread-p4"
        msg = message_bus.send_message(
            sender="researcher",
            recipient="supervisor",
            content="Found 3 relevant sources for query.",
            summary="Research complete",
            thread_id=tid,
        )
        self.assertEqual(msg.sender, "researcher")
        self.assertEqual(msg.recipient, "supervisor")

        # Query messages for recipient
        sup_msgs = message_bus.get_messages(thread_id=tid, recipient="supervisor")
        self.assertEqual(len(sup_msgs), 1)
        self.assertEqual(sup_msgs[0].content, "Found 3 relevant sources for query.")

    def test_research_agent(self):
        tid = "test-thread-p4"
        res = research_agent.research(
            topic="LangChain and multi-agent systems",
            thread_id=tid,
            include_web=False,
            include_docs=False,
        )
        self.assertEqual(res["status"], "completed")
        self.assertIn("Research Findings", res["report"])

    def test_coding_agent_syntax_and_execution(self):
        tid = "test-thread-p4"
        # Valid code execution
        code = "val = 21 * 2\nprint('Result is', val)"
        res = run_code_task.invoke({
            "task": "Compute double of 21",
            "thread_id": tid,
            "filename": "calc.py",
            "code": code,
            "run_code": True,
        })
        self.assertTrue(res["syntax_valid"])
        self.assertEqual(res["status"], "completed")
        self.assertIn("execution", res)

        # Invalid syntax detection
        bad_code = "def broken(:\n  pass"
        bad_res = run_code_task.invoke({
            "task": "Check invalid syntax",
            "thread_id": tid,
            "code": bad_code,
        })
        self.assertFalse(bad_res["syntax_valid"])
        self.assertIn("syntax_error", bad_res)

    def test_data_analyst_agent(self):
        tid = "test-thread-p4"
        csv_sample = "category,revenue\nSaaS,5000\nServices,3000"
        res = run_data_analysis.invoke({
            "task": "Summarize revenue by category",
            "csv_data": csv_sample,
            "sql_query": "SELECT 1 as test_col",
            "thread_id": tid,
        })
        self.assertEqual(res["status"], "completed")
        self.assertIn("tabular_analysis", res)
        self.assertIn("sql_result", res)

    def test_supervisor_classification_and_delegation(self):
        # 1. Classification
        self.assertEqual(supervisor_agent.classify_intent("Write a python script to parse logs"), AgentRole.CODER)
        self.assertEqual(supervisor_agent.classify_intent("Compute average from this CSV table"), AgentRole.DATA_ANALYST)
        self.assertEqual(supervisor_agent.classify_intent("Search web for latest AI news"), AgentRole.RESEARCHER)

        # 2. Delegation via tool
        del_res = route_to_specialist.invoke({
            "task": "Write a python function to compute factorial",
            "thread_id": "test-thread-p4",
            "role": "coder",
            "code": "def fact(n):\n    return 1 if n <= 1 else n * fact(n-1)\nprint(fact(4))",
            "filename": "factorial.py",
        })
        self.assertEqual(del_res["assigned_agent"], "coder")
        self.assertEqual(del_res["status"], "completed")

    def test_mcp_server_protocol(self):
        # 1. initialize
        init_res = mcp_server.handle_request({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
        })
        self.assertEqual(init_res["jsonrpc"], "2.0")
        self.assertEqual(init_res["result"]["protocolVersion"], "2024-11-05")

        # 2. tools/list
        list_res = mcp_server.handle_request({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
        })
        tools = list_res["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("web_search", tool_names)
        self.assertIn("read_workspace_file", tool_names)
        self.assertIn("query_database", tool_names)

        # 3. tools/call
        call_res = mcp_server.handle_request({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "query_database",
                "arguments": {"query": "SELECT 1 as test_val"},
            },
        })
        self.assertFalse(call_res["result"]["isError"])
        content = call_res["result"]["content"]
        self.assertGreaterEqual(len(content), 1)

        # 4. Unknown method
        err_res = mcp_server.handle_request({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "non_existent_method",
        })
        self.assertIn("error", err_res)
        self.assertEqual(err_res["error"]["code"], -32601)

    def test_mcp_api_endpoint(self):
        response = self.client.post("/mcp", json={
            "jsonrpc": "2.0",
            "id": 10,
            "method": "initialize",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["result"]["protocolVersion"], "2024-11-05")


if __name__ == "__main__":
    unittest.main()
