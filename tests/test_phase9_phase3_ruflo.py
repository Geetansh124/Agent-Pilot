"""Unit tests for Phase 3 Ruflo integration components.

Tests Browser Tester, Automated Doc Generator, Architecture Decision Records (ADR),
and SPARC 5-phase Development Methodology.
"""
import unittest

from src.tools.browser_tester import BrowserTester
from src.tools.doc_generator import DocGenerator
from src.architecture.adr_manager import ADRManager, ADRStatus
from src.methodology.sparc import SPARCOrchestrator, SPARCPhase


class TestBrowserTester(unittest.TestCase):
    """Test browser and DOM validation."""

    def setUp(self):
        self.tester = BrowserTester()

    def test_dom_string_validation(self):
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>My Test Page</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body>
            <h1>Welcome to Agent-Pilot</h1>
            <h2>Subheading</h2>
        </body>
        </html>
        """
        res = self.tester.test_dom_string(html)
        self.assertTrue(res["valid_html"])
        self.assertEqual(res["title"], "My Test Page")
        self.assertIn("Welcome to Agent-Pilot", res["headings"])
        self.assertTrue(res["has_viewport_meta"])
        self.assertEqual(res["quality_score"], 100)


class TestDocGenerator(unittest.TestCase):
    """Test automated markdown documentation generator from AST."""

    def setUp(self):
        self.generator = DocGenerator()

    def test_generate_markdown_docs(self):
        code = '''"""Sample math module."""

class VectorMath:
    """Performs 3D vector computations."""

    def dot_product(self, u: list, v: list) -> float:
        """Calculate dot product of two vectors."""
        return sum(x * y for x, y in zip(u, v))

def add_scalars(a: int, b: int) -> int:
    """Add two integer scalars."""
    return a + b
'''
        res = self.generator.generate_markdown_docs(code, module_name="vector_math")
        md = res["markdown"]
        self.assertIn("# `vector_math` Documentation", md)
        self.assertIn("class VectorMath", md)
        self.assertIn("def dot_product", md)
        self.assertIn("def add_scalars", md)
        self.assertEqual(res["classes_documented"], 1)
        self.assertEqual(res["functions_documented"], 1)


class TestADRManager(unittest.TestCase):
    """Test Architecture Decision Record storage, querying, and markdown export."""

    def setUp(self):
        self.manager = ADRManager(db_path=":memory:")

    def test_create_and_retrieve_adr(self):
        res = self.manager.create_adr(
            title="Adopt SQLite for Embedded Knowledge Graph",
            context="Need zero-overhead relational and property graph storage.",
            decision="Store nodes and edges in local SQLite tables with BFS traversal.",
            consequences="Fast local queries without needing Neo4j server daemon.",
            tags=["storage", "graph", "database"],
        )
        self.assertEqual(res["status"], "created")
        adr_id = res["adr_id"]

        record = self.manager.get_adr(adr_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["title"], "Adopt SQLite for Embedded Knowledge Graph")
        self.assertIn("ADR-0001", record["markdown"])
        self.assertIn("Adopt SQLite", record["markdown"])

    def test_list_adrs(self):
        self.manager.create_adr("ADR 1", "ctx1", "dec1", "conseq1")
        self.manager.create_adr("ADR 2", "ctx2", "dec2", "conseq2")
        adrs = self.manager.list_adrs()
        self.assertEqual(len(adrs), 2)


class TestSPARCOrchestrator(unittest.TestCase):
    """Test SPARC 5-phase lifecycle advancement."""

    def setUp(self):
        self.sparc = SPARCOrchestrator()

    def test_full_sparc_lifecycle(self):
        # S: Specification
        proj = self.sparc.start_feature("Vector Cache", "Implement in-memory LRU vector cache.")
        proj_id = proj.project_id
        self.assertEqual(proj.current_phase, SPARCPhase.PSEUDOCODE)

        # P: Pseudocode
        res_p = self.sparc.advance_phase(proj_id, {"pseudocode": "class Cache: def get()..."})
        self.assertEqual(res_p["next_phase"], SPARCPhase.ARCHITECTURE.value)

        # A: Architecture
        res_a = self.sparc.advance_phase(proj_id, {"interfaces": ["ICache", "LRUPolicy"]})
        self.assertEqual(res_a["next_phase"], SPARCPhase.REFINEMENT.value)

        # R: Refinement
        res_r = self.sparc.advance_phase(proj_id, {"code": "class LRUCache...", "tests_passed": True})
        self.assertEqual(res_r["next_phase"], SPARCPhase.COMPLETION.value)

        # C: Completion
        res_c = self.sparc.advance_phase(proj_id, {"final_status": "ready", "docs": "markdown"})
        self.assertEqual(res_c["status"], "completed")


if __name__ == "__main__":
    unittest.main()
