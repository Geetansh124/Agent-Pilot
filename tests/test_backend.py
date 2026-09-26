import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from api_server import app
from langraph_rag_backend import (
    _route_with_ruflo,
    calculator,
    delete_thread,
    get_stock_price,
    retrieve_all_threads,
    conn,
)


class TestBackend(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    # ---------------------- Health ----------------------

    def test_api_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    # ---------------------- Threads ----------------------

    def test_create_thread(self):
        response = self.client.post("/api/threads")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("id", data)
        self.assertEqual(data["title"], "New chat")

    def test_delete_thread_nonexistent(self):
        response = self.client.delete("/api/threads/nonexistent-thread-id")
        # delete_thread returns True even if no rows matched (DELETE is idempotent)
        self.assertIn(response.status_code, [200, 404])

    def test_rename_thread(self):
        response = self.client.patch(
            "/api/threads/rename-test-id",
            json={"title": "Renamed Project Discussion"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"id": "rename-test-id", "title": "Renamed Project Discussion"})

    def test_rename_thread_empty_reject(self):
        response = self.client.patch(
            "/api/threads/rename-test-id",
            json={"title": "   "},
        )
        self.assertEqual(response.status_code, 422)

    def test_rate_limit_enforcement(self):
        from api_server import _check_rate_limit
        from fastapi import HTTPException
        # Simulating 60 rapid requests
        test_ip = "192.168.1.99"
        for _ in range(60):
            _check_rate_limit(test_ip)
        with self.assertRaises(HTTPException) as ctx:
            _check_rate_limit(test_ip)
        self.assertEqual(ctx.exception.status_code, 429)

    # ---------------------- SSE Streaming ----------------------

    @patch("api_server.chatbot.stream")
    def test_chat_stream_endpoint_exists(self, mock_stream):
        """Verify the SSE endpoint streams events properly."""
        mock_stream.return_value = iter([
            (AIMessage(content="Hello world"), None)
        ])
        response = self.client.post(
            "/api/chat/stream",
            json={"message": "hello", "thread_id": "test-sse-thread"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        self.assertIn("Hello world", response.text)

    # ---------------------- Ruflo ----------------------

    @patch("subprocess.run")
    def test_ruflo_route_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='Result: {"task": "test task", "agent": "coder"}',
            stderr="",
        )
        result = _route_with_ruflo("test task")
        self.assertIn("task", result)
        self.assertEqual(result["task"], "test task")

    @patch("subprocess.run")
    def test_ruflo_route_missing_npx_fallback(self, mock_run):
        mock_run.side_effect = FileNotFoundError("npx not found")
        result = _route_with_ruflo("test fallback")
        self.assertIn("error", result)
        self.assertIn("Ruflo is unavailable", result["error"])

    # ---------------------- Tools ----------------------

    def test_calculator_tool(self):
        res = calculator.invoke({"first_num": 10, "second_num": 5, "operation": "add"})
        self.assertEqual(
            res,
            {"first_num": 10, "second_num": 5, "operation": "add", "result": 15},
        )

        div_zero = calculator.invoke(
            {"first_num": 10, "second_num": 0, "operation": "div"}
        )
        self.assertEqual(div_zero, {"error": "Division by zero is not allowed"})

    def test_calculator_operations(self):
        sub = calculator.invoke({"first_num": 10, "second_num": 3, "operation": "sub"})
        self.assertEqual(sub["result"], 7)

        mul = calculator.invoke({"first_num": 4, "second_num": 5, "operation": "mul"})
        self.assertEqual(mul["result"], 20)

        div = calculator.invoke({"first_num": 15, "second_num": 3, "operation": "div"})
        self.assertEqual(div["result"], 5.0)

        bad_op = calculator.invoke(
            {"first_num": 1, "second_num": 1, "operation": "mod"}
        )
        self.assertIn("error", bad_op)

    def test_retrieve_all_threads_performance_and_correctness(self):
        cursor = conn.cursor()
        cursor.execute("DELETE FROM checkpoints WHERE thread_id IN ('perf_test_1', 'perf_test_2')")
        cursor.execute(
            "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id) VALUES (?, ?, ?)",
            ("perf_test_1", "", "cp_1"),
        )
        cursor.execute(
            "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id) VALUES (?, ?, ?)",
            ("perf_test_1", "", "cp_2"),
        )
        cursor.execute(
            "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id) VALUES (?, ?, ?)",
            ("perf_test_2", "", "cp_3"),
        )
        conn.commit()

        try:
            threads = retrieve_all_threads()
            self.assertIn("perf_test_1", threads)
            self.assertIn("perf_test_2", threads)
            self.assertEqual(len(threads), len(set(threads)))
        finally:
            cursor.execute("DELETE FROM checkpoints WHERE thread_id IN ('perf_test_1', 'perf_test_2')")
            conn.commit()

    def test_delete_thread_cleans_up(self):
        cursor = conn.cursor()
        cursor.execute("DELETE FROM checkpoints WHERE thread_id = 'delete_test_thread'")
        cursor.execute(
            "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id) VALUES (?, ?, ?)",
            ("delete_test_thread", "", "cp_del_1"),
        )
        conn.commit()

        result = delete_thread("delete_test_thread")
        self.assertTrue(result)

        cursor.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?",
            ("delete_test_thread",),
        )
        self.assertEqual(cursor.fetchone()[0], 0)

    # ---------------------- Agent Tools ----------------------

    def test_agent_python_interpreter(self):
        from agent_tools import python_interpreter

        res = python_interpreter.invoke({"code": "x = 10 * 5\nprint('Computed:', x)"})
        self.assertTrue(res["success"])
        self.assertIn("Computed: 50", res["stdout"])
        self.assertEqual(res["variables"].get("x"), "50")

    def test_agent_python_interpreter_security(self):
        from agent_tools import python_interpreter

        res = python_interpreter.invoke({"code": "import os\nos.listdir('.')"})
        self.assertFalse(res["success"])
        self.assertIn("restricted", res["error"].lower())

    def test_agent_get_current_datetime(self):
        from agent_tools import get_current_datetime

        res = get_current_datetime.invoke({})
        self.assertIn("utc_iso", res)
        self.assertIn("year", res)
        self.assertGreaterEqual(res["year"], 2026)

    def test_agent_analyze_tabular_data(self):
        from agent_tools import analyze_tabular_data

        csv_data = "name,score\nAlice,95\nBob,85\nCharlie,90"
        res = analyze_tabular_data.invoke({"data": csv_data})
        self.assertEqual(res["total_rows"], 3)
        self.assertEqual(res["total_columns"], 2)
        self.assertIn("score", res["summary"])
        self.assertEqual(res["summary"]["score"]["max"], 95.0)

    def test_agent_analyze_tabular_json(self):
        from agent_tools import analyze_tabular_data
        import json

        json_data = json.dumps([{"name": "A", "val": 1}, {"name": "B", "val": 2}])
        res = analyze_tabular_data.invoke({"data": json_data})
        self.assertEqual(res["total_rows"], 2)
        self.assertIn("name", res["columns"])

    def test_agent_fetch_web_url_bad_scheme(self):
        from agent_tools import fetch_web_url

        res = fetch_web_url.invoke({"url": "ftp://example.com"})
        self.assertIn("error", res)

    # ---------------------- API Validation ----------------------

    def test_chat_requires_message(self):
        response = self.client.post(
            "/api/chat", json={"message": "", "thread_id": "t1"}
        )
        self.assertEqual(response.status_code, 422)

    def test_upload_rejects_unsupported_format(self):
        from io import BytesIO

        response = self.client.post(
            "/api/threads/test-thread/document",
            files={"file": ("malicious.exe", BytesIO(b"binary content"), "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 415)

    def test_upload_accepts_txt_document(self):
        from io import BytesIO

        response = self.client.post(
            "/api/threads/test-thread-txt/document",
            files={"file": ("project_notes.txt", BytesIO(b"Quarterly business results: Q1 revenue was $5M."), "text/plain")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["filename"], "project_notes.txt")
        self.assertGreaterEqual(data["chunks"], 1)

    # ---------------------- Phase 2 Tools ----------------------

    def test_document_loader_txt_and_csv(self):
        from src.tools.document_loader import load_document_from_bytes

        # TXT
        txt_docs = load_document_from_bytes(b"DocuPilot AI system architecture notes.", "system.md")
        self.assertEqual(len(txt_docs), 1)
        self.assertIn("architecture", txt_docs[0].page_content)

        # CSV
        csv_bytes = b"city,population\nTokyo,37000000\nDelhi,32000000\nShanghai,29000000"
        csv_docs = load_document_from_bytes(csv_bytes, "cities.csv")
        self.assertEqual(len(csv_docs), 1)
        self.assertIn("Tokyo", csv_docs[0].page_content)

    def test_document_loader_docx(self):
        from src.tools.document_loader import load_document_from_bytes
        import docx
        import io

        doc = docx.Document()
        doc.add_paragraph("Sample DOCX document paragraph.")
        buf = io.BytesIO()
        doc.save(buf)

        docx_docs = load_document_from_bytes(buf.getvalue(), "sample.docx")
        self.assertEqual(len(docx_docs), 1)
        self.assertIn("Sample DOCX", docx_docs[0].page_content)

    @patch("duckduckgo_search.DDGS.text")
    def test_web_search_fallback(self, mock_ddg):
        from src.tools.web_search import web_search

        mock_ddg.return_value = [
            {"title": "Python 3.13 Released", "href": "https://python.org", "body": "Python 3.13 features"}
        ]
        res = web_search.invoke({"query": "python 3.13 release"})
        self.assertIn("results", res)
        self.assertEqual(res["results"][0]["title"], "Python 3.13 Released")

    def test_scrape_web_ssrf_protection(self):
        from src.tools.web_scrape import scrape_web

        res_local = scrape_web.invoke({"url": "http://127.0.0.1:8080/admin"})
        self.assertIn("error", res_local)
        self.assertIn("prohibited", res_local["error"].lower())

        res_loopback = scrape_web.invoke({"url": "http://localhost/secret"})
        self.assertIn("error", res_loopback)

    @patch("requests.get")
    def test_scrape_web_parsing(self, mock_get):
        from src.tools.web_scrape import scrape_web

        html = """
        <html>
            <head><title>Test Article</title><meta name="description" content="Article summary"></head>
            <body>
                <h1>Main Heading</h1>
                <p>First informative paragraph containing more than forty characters of text content.</p>
                <a href="https://example.com/details">Read more</a>
            </body>
        </html>
        """
        mock_get.return_value = MagicMock(status_code=200, text=html, ok=True)
        res = scrape_web.invoke({"url": "https://example.com/article"})
        self.assertEqual(res["title"], "Test Article")
        self.assertIn("H1: Main Heading", res["headings"])
        self.assertIn("First informative paragraph", res["content"])

    def test_workspace_file_tools(self):
        from src.tools.file_tools import (
            read_workspace_file,
            write_workspace_file,
            list_workspace_files,
            delete_workspace_file,
        )

        tid = "test-ws-thread"
        # Write
        w_res = write_workspace_file.invoke({"filename": "report.txt", "content": "Q1 Performance: Excellent", "thread_id": tid})
        self.assertTrue(w_res["success"])

        # Read
        r_res = read_workspace_file.invoke({"filename": "report.txt", "thread_id": tid})
        self.assertTrue(r_res["success"])
        self.assertEqual(r_res["content"], "Q1 Performance: Excellent")

        # List
        l_res = list_workspace_files.invoke({"thread_id": tid})
        self.assertTrue(l_res["success"])
        names = [f["name"] for f in l_res["files"]]
        self.assertIn("report.txt", names)

        # Path traversal guard
        bad_res = write_workspace_file.invoke({"filename": "../../../outside.txt", "content": "hack", "thread_id": tid})
        self.assertFalse(bad_res["success"])
        self.assertIn("denied", bad_res["error"].lower())

        # Delete
        d_res = delete_workspace_file.invoke({"filename": "report.txt", "thread_id": tid})
        self.assertTrue(d_res["success"])

    def test_query_database_safety_and_select(self):
        from src.tools.database_tool import query_database

        # Valid SELECT
        res = query_database.invoke({"query": "SELECT name FROM sqlite_master WHERE type='table'"})
        self.assertTrue(res["success"])
        self.assertIn("columns", res)

        # Blocked DROP TABLE
        bad_drop = query_database.invoke({"query": "DROP TABLE checkpoints"})
        self.assertFalse(bad_drop["success"])
        self.assertIn("prohibited", bad_drop["error"].lower())

        # Blocked DELETE
        bad_delete = query_database.invoke({"query": "DELETE FROM checkpoints"})
        self.assertFalse(bad_delete["success"])

    def test_call_api_ssrf_and_methods(self):
        from src.tools.api_caller import call_api

        # SSRF blocked
        res_ssrf = call_api.invoke({"url": "http://127.0.0.1:5000/data"})
        self.assertFalse(res_ssrf["success"])
        self.assertIn("forbidden", res_ssrf["error"].lower())

        # Unsupported method
        res_method = call_api.invoke({"url": "https://api.example.com", "method": "TRACE"})
        self.assertFalse(res_method["success"])
        self.assertIn("unsupported", res_method["error"].lower())


if __name__ == "__main__":
    unittest.main()
