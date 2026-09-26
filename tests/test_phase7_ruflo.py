"""Unit tests for Phase 1 Ruflo integration components.

Tests Swarm Coordinator, Self-Learning Engine, Graph-Enhanced RAG, and Testing Agent.
"""
import unittest
from unittest.mock import MagicMock, patch

from src.agents.shared_state import AgentRole, InterAgentMessageBus
from src.agents.swarm_coordinator import SwarmCoordinator, SwarmTopology, AgentTask
from src.intelligence.learning_engine import SelfLearningEngine
from src.rag.graph_rag import GraphRAGRetriever
from src.tools.test_generator import generate_unit_tests, run_test_suite
from src.agents.testing_agent import TestingAgent


class TestSwarmCoordinator(unittest.TestCase):
    """Test swarm coordinator topologies and execution."""

    def setUp(self):
        self.coordinator = SwarmCoordinator(max_workers=2)

    def test_pipeline_execution(self):
        """Test pipeline execution topology."""
        tasks = [
            AgentTask(agent_role=AgentRole.RESEARCHER, task_input="Gather data"),
            AgentTask(agent_role=AgentRole.CODER, task_input="Write code"),
        ]
        result = self.coordinator.execute_swarm(
            topology=SwarmTopology.PIPELINE,
            tasks=tasks,
            thread_id="test_thread",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["topology"], "pipeline")
        self.assertEqual(result["completed_tasks"], 2)

    def test_fan_out_execution(self):
        """Test fan_out parallel execution topology."""
        tasks = [
            AgentTask(agent_role=AgentRole.RESEARCHER, task_input="Research item 1"),
            AgentTask(agent_role=AgentRole.RESEARCHER, task_input="Research item 2"),
        ]
        result = self.coordinator.execute_swarm(
            topology=SwarmTopology.FAN_OUT,
            tasks=tasks,
            thread_id="test_thread",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["completed_tasks"], 2)


class TestLearningEngine(unittest.TestCase):
    """Test self-learning engine."""

    def setUp(self):
        self.engine = SelfLearningEngine(storage_path=":memory:")

    def test_record_and_recommend_routing(self):
        """Test recording an outcome and getting routing recommendations."""
        self.engine.record_outcome(
            task="Write a python sorting algorithm",
            chosen_agent="coder",
            tools_used=["write_workspace_file"],
            success=True,
            duration_ms=450,
            feedback_score=1.0,
        )
        rec = self.engine.recommend_agent(task="write a function in python")
        self.assertIn("recommended_agent", rec)
        self.assertEqual(rec["recommended_agent"], "coder")

    def test_pattern_extraction(self):
        """Test tool sequence pattern analysis."""
        for _ in range(3):
            self.engine.record_outcome(
                task="Analyze sales report",
                chosen_agent="data-analyst",
                tools_used=["query_database"],
                success=True,
                duration_ms=200,
            )
        patterns = self.engine.get_learned_patterns()
        self.assertIn("data-analyst", patterns.get("agent_profiles", {}))


class TestTestGenerator(unittest.TestCase):
    """Test AST-based test generation tool."""

    def test_generate_tests_for_code(self):
        code = '''
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

class Calculator:
    def multiply(self, x: float, y: float) -> float:
        return x * y
'''
        res = generate_unit_tests(code=code, module_name="calc")
        self.assertEqual(res["status"], "success")
        self.assertIn("def test_add", res["generated_test_code"])
        self.assertIn("class TestCalculator", res["generated_test_code"])
        self.assertIn("def test_multiply", res["generated_test_code"])


class TestTestingAgent(unittest.TestCase):
    """Test testing agent execution."""

    def test_testing_agent_routing(self):
        agent = TestingAgent()
        res = agent.run_tests_or_generate(
            task="Generate tests for this function",
            code="def square(x): return x * x\n",
        )
        self.assertEqual(res["status"], "completed")
        self.assertIn("test_square", res["test_suite"])



if __name__ == "__main__":
    unittest.main()
