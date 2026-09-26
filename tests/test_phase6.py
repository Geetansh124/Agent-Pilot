import io
import unittest
from fastapi.testclient import TestClient

from api_server import app
from src.agent.critic import critic_agent, evaluate_response
from src.automation import schedule_recurring_task, task_scheduler, workflow_runner
from src.graph import knowledge_graph, query_knowledge_graph
from src.voice import audio_processor


class TestPhase6AdvancedAgenticSystem(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_knowledge_graph_extraction_and_traversal(self):
        # 1. Add nodes and edges
        knowledge_graph.add_edge("LangGraph", "USES", "SQLite", weight=1.0)
        knowledge_graph.add_edge("DocuPilot", "IMPLEMENTS", "LangGraph", weight=1.0)
        knowledge_graph.add_edge("LangGraph", "USES", "FAISS", weight=1.0)

        # 2. Query subgraph
        subgraph = knowledge_graph.query_subgraph("DocuPilot", max_depth=2)
        self.assertGreaterEqual(subgraph["total_nodes"], 2)
        self.assertGreaterEqual(subgraph["total_edges"], 2)
        node_labels = [n["label"].lower() for n in subgraph["nodes"]]
        self.assertIn("langgraph", node_labels)

        # 3. Triple extraction
        sample_text = "FastAPI uses Starlette and LangChain implements Agents."
        triples = knowledge_graph.extract_triples_from_text(sample_text)
        self.assertGreaterEqual(len(triples), 1)

        # 4. Tool invocation
        tool_res = query_knowledge_graph.invoke({"entity": "LangGraph"})
        self.assertEqual(tool_res["root"], "langgraph")

    def test_task_scheduler(self):
        # 1. Schedule task
        task = task_scheduler.schedule("SyncDocumentIndex", interval_seconds=30)
        self.assertEqual(task.status, "active")
        self.assertEqual(task.run_count, 0)
        tid = task.task_id

        # 2. Mark executed
        task_scheduler.mark_executed(tid, "Synced 5 files")
        self.assertEqual(task.run_count, 1)
        self.assertIn("Synced", task.last_run_result)

        # 3. List tasks
        active = task_scheduler.list_tasks()
        self.assertTrue(any(t["task_id"] == tid for t in active))

        # 4. Cancel
        cancelled = task_scheduler.cancel(tid)
        self.assertTrue(cancelled)

    def test_autonomous_workflow_runner(self):
        # Register test dummy tool
        workflow_runner.register_tool("echo_tool", lambda msg: f"Echo: {msg}")
        workflow_runner.register_tool("uppercase_tool", lambda text: text.upper())

        steps = [
            {"name": "step1", "tool": "echo_tool", "arguments": {"msg": "hello world"}},
            {"name": "step2", "tool": "uppercase_tool", "arguments": {"text": "{{step1}}"}},
        ]
        result = workflow_runner.run_workflow("TestEchoPipeline", steps)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["steps_executed"], 2)
        self.assertEqual(result["final_context"]["step2"], "ECHO: HELLO WORLD")

    def test_voice_processor(self):
        # 1. Transcription
        dummy_wav = b"RIFF" + b"\x00" * 40
        tr_res = audio_processor.transcribe(dummy_wav, filename="query.wav")
        self.assertEqual(tr_res["status"], "transcribed")
        self.assertGreater(tr_res["estimated_duration_sec"], 0)

        # 2. Synthesis
        syn_res = audio_processor.synthesize("Welcome to DocuPilot AI Assistant.")
        self.assertEqual(syn_res["audio_format"], "audio/wav")
        self.assertIn("audio_base64", syn_res)

    def test_critic_agent_evaluation(self):
        # 1. High-fidelity answer
        context = "The DocuPilot architecture utilizes LangGraph for DAG state persistence and FAISS for MMR retrieval."
        good_response = "DocuPilot uses LangGraph for state persistence and FAISS for retrieval [doc.pdf, Page 1]."
        good_eval = critic_agent.evaluate(
            question="What does DocuPilot use for retrieval?",
            context=context,
            response=good_response,
        )
        self.assertTrue(good_eval["is_acceptable"])
        self.assertGreaterEqual(good_eval["score"], 0.65)
        self.assertFalse(good_eval["hallucination_detected"])

        # 2. Hallucinatory / ungrounded answer
        bad_response = "DocuPilot is an airplane navigation system that steers commercial airlines through storm clouds."
        bad_eval = critic_agent.evaluate(
            question="What does DocuPilot use for retrieval?",
            context=context,
            response=bad_response,
        )
        self.assertTrue(bad_eval["hallucination_detected"])
        self.assertFalse(bad_eval["is_acceptable"])

    def test_phase6_api_endpoints(self):
        # 1. Knowledge graph
        g_resp = self.client.get("/api/graph/LangGraph")
        self.assertEqual(g_resp.status_code, 200)

        # 2. Task scheduling
        s_resp = self.client.post("/api/automation/schedule", json={
            "name": "DailyResearchReport",
            "interval_seconds": 86400,
        })
        self.assertEqual(s_resp.status_code, 200)
        self.assertIn("task_id", s_resp.json())

        # 3. Tasks list
        t_resp = self.client.get("/api/automation/tasks")
        self.assertEqual(t_resp.status_code, 200)

        # 4. Voice transcription
        audio_file = io.BytesIO(b"RIFF" + b"\x00" * 40)
        v_resp = self.client.post("/api/voice/transcribe", files={"file": ("prompt.wav", audio_file, "audio/wav")})
        self.assertEqual(v_resp.status_code, 200)
        self.assertIn("transcript", v_resp.json())

        # 5. Voice synthesis
        syn_resp = self.client.post("/api/voice/synthesize", json={"text": "Synthesizing test speech."})
        self.assertEqual(syn_resp.status_code, 200)
        self.assertIn("audio_base64", syn_resp.json())

        # 6. Critic evaluation
        crit_resp = self.client.post("/api/agent/critique", json={
            "question": "What is Python?",
            "context": "Python is a high-level general-purpose programming language.",
            "response": "Python is a programming language [Doc, Page 1].",
        })
        self.assertEqual(crit_resp.status_code, 200)
        self.assertIn("score", crit_resp.json())


if __name__ == "__main__":
    unittest.main()
