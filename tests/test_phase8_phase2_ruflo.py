"""Unit tests for Phase 2 Ruflo integration components.

Tests PageRank Graph Intelligence, PII Detection, Vulnerability Scanning,
3-Tier LLM Routing, Distributed Tracing, Autopilot Engine, and Federation Network.
"""
import unittest

from src.graph.knowledge_graph import KnowledgeGraph
from src.security.pii_detector import PIIDetector
from src.security.vulnerability_scanner import VulnerabilityScanner
from src.llm.router import ModelRouter, ModelTier
from src.observability.tracing import AgentTracer
from src.agent.autopilot import AutopilotEngine, AutopilotStatus
from src.federation.node import FederationNetwork


class TestGraphIntelligence(unittest.TestCase):
    """Test PageRank computation and query complexity estimation."""

    def setUp(self):
        self.kg = KnowledgeGraph(db_path=":memory:")
        self.kg.add_edge("AgentA", "CALLS", "AgentB")
        self.kg.add_edge("AgentB", "CALLS", "AgentC")
        self.kg.add_edge("AgentC", "CALLS", "AgentA")

    def test_pagerank_computation(self):
        ranks = self.kg.compute_pagerank()
        self.assertIn("agenta", ranks)
        self.assertIn("agentb", ranks)
        self.assertIn("agentc", ranks)
        self.assertAlmostEqual(sum(ranks.values()), 1.0, places=3)

    def test_query_complexity_estimation(self):
        comp = self.kg.estimate_query_complexity("agenta", max_depth=2)
        self.assertTrue(comp["safe_to_traverse"])
        self.assertEqual(comp["complexity_risk"], "low")

    def test_delta_update(self):
        triples = [("AgentD", "USES", "ToolE"), ("ToolE", "OUTPUTS", "DataF")]
        res = self.kg.delta_update(triples)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["edges_added"], 2)


class TestSecurityEngines(unittest.TestCase):
    """Test PII detection and static vulnerability scanner."""

    def setUp(self):
        self.pii = PIIDetector()
        self.vuln = VulnerabilityScanner()

    def test_pii_detection_and_masking(self):
        text = "Contact john.doe@example.com or call 555-123-4567 with SSN 123-45-6789."
        res = self.pii.mask_text(text)
        self.assertTrue(res["pii_detected"])
        self.assertIn("EMAIL", res["pii_types"])
        self.assertIn("PHONE", res["pii_types"])
        self.assertIn("SSN", res["pii_types"])
        self.assertNotIn("john.doe@example.com", res["sanitized_text"])
        self.assertNotIn("123-45-6789", res["sanitized_text"])

    def test_vulnerability_scanner_detects_eval(self):
        code = '''
def run_dynamic(user_input):
    return eval(user_input)
'''
        res = self.vuln.scan_code(code, "test.py")
        self.assertEqual(res["status"], "vulnerable")
        self.assertTrue(any(f["vuln_type"] == "INSECURE_DYNAMIC_EXECUTION" for f in res["findings"]))

    def test_vulnerability_scanner_detects_shell_injection(self):
        code = '''
import subprocess
def exec_cmd(cmd):
    subprocess.Popen(cmd, shell=True)
'''
        res = self.vuln.scan_code(code, "test.py")
        self.assertEqual(res["status"], "vulnerable")
        self.assertTrue(any(f["vuln_type"] == "COMMAND_INJECTION_RISK" for f in res["findings"]))


class TestModelRouter(unittest.TestCase):
    """Test 3-tier task classification and model selection."""

    def setUp(self):
        self.router = ModelRouter()

    def test_tier_classification(self):
        fast_tier = self.router.classify_task_tier("clean up this string")
        self.assertEqual(fast_tier, ModelTier.TIER_1_FAST)

        reasoning_tier = self.router.classify_task_tier("Design a distributed multi-agent system architecture")
        self.assertEqual(reasoning_tier, ModelTier.TIER_3_REASONING)

    def test_model_selection(self):
        res = self.router.select_model("Refactor and optimize algorithm for concurrency")
        self.assertEqual(res["tier"], ModelTier.TIER_3_REASONING.value)
        self.assertIn("selected_model", res)
        self.assertGreater(len(res["fallback_chain"]), 0)


class TestTracingEngine(unittest.TestCase):
    """Test distributed trace spans and parent-child contexts."""

    def setUp(self):
        self.tracer = AgentTracer()

    def test_span_lifecycle_and_hierarchy(self):
        root = self.tracer.start_trace("supervisor.run")
        child = self.tracer.start_span("agent.coder", trace_id=root.trace_id, parent_span_id=root.span_id)
        child.add_event("start_codegen", {"file": "app.py"})
        child.finish(status="OK")
        root.finish(status="OK")

        summary = self.tracer.export_trace_summary(root.trace_id)
        self.assertEqual(summary["span_count"], 2)
        self.assertFalse(summary["has_errors"])
        self.assertGreaterEqual(summary["total_duration_ms"], 0.0)


class TestAutopilotEngine(unittest.TestCase):
    """Test autonomous mission planning and execution loop."""

    def test_autopilot_mission_execution(self):
        def dummy_executor(step_desc: str, context: dict) -> str:
            return f"Executed: {step_desc}"

        engine = AutopilotEngine(step_executor=dummy_executor)
        res = engine.run_mission("Build automated reporting pipeline", max_iterations=5)
        self.assertEqual(res["status"], AutopilotStatus.COMPLETED.value)
        self.assertEqual(len(res["steps"]), 3)
        self.assertEqual(res["steps"][0]["status"], "completed")


class TestFederationNetwork(unittest.TestCase):
    """Test federation multi-node registration, envelope signing, and verification."""

    def setUp(self):
        self.net = FederationNetwork(local_node_id="node-test-1", secret_key="super-secret")

    def test_node_registration_and_listing(self):
        self.net.register_node(
            node_id="node-worker-2",
            endpoint_url="http://192.168.1.50:8000",
            available_agents=["coder", "testing"],
        )
        nodes = self.net.list_nodes()
        self.assertEqual(len(nodes), 2)

    def test_envelope_signature_verification(self):
        envelope = self.net.create_envelope(
            target_node="node-worker-2",
            recipient_agent="coder",
            payload={"code": "print('hello')"},
        )
        self.assertTrue(self.net.verify_signature(envelope))

        # Tampered envelope should fail verification
        envelope.payload["code"] = "print('tampered')"
        self.assertFalse(self.net.verify_signature(envelope))


if __name__ == "__main__":
    unittest.main()
