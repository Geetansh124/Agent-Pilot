import unittest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage

from src.agent.planner import create_plan, reflect_on_goal, update_plan_step
from src.memory.memory_store import MemoryStore, delete_memory, retrieve_memory, store_memory
from src.memory.summarizer import summarize_conversation_messages
from src.rag.hybrid_retriever import HybridRetriever, bm25_sparse_score
from src.rag.multi_doc_manager import multi_doc_manager
from langraph_rag_backend import rag_tool, ingest_pdf


class TestPhase3Capabilities(unittest.TestCase):
    def test_memory_store_retrieve_and_delete(self):
        tid = "test-mem-thread-1"
        res = store_memory.invoke({
            "content": "User prefers concise answers with Python 3.12 code examples.",
            "category": "preference",
            "namespace": tid,
        })
        self.assertEqual(res["status"], "stored")
        mem_id = res["id"]

        # Retrieve matching keyword
        retrieved = retrieve_memory.invoke({
            "query": "What language does the user prefer?",
            "namespace": tid,
            "limit": 3,
        })
        self.assertGreaterEqual(len(retrieved), 1)
        self.assertIn("Python", retrieved[0]["content"])

        # Clean up
        store = MemoryStore()
        deleted = store.delete(mem_id)
        self.assertTrue(deleted)

    def test_conversation_summarizer(self):
        # Build 14 messages (exceeds threshold 10)
        messages = []
        for i in range(7):
            messages.append(HumanMessage(content=f"Question number {i}: Can you explain topic {i}?"))
            messages.append(AIMessage(content=f"Answer number {i}: Topic {i} is related to quantum mechanics and computing."))

        compressed = summarize_conversation_messages(messages, threshold=10, keep_recent=4)
        self.assertEqual(len(compressed), 5)  # 1 summary + 4 recent
        self.assertEqual(compressed[0].type, "system")
        self.assertIn("PREVIOUS CONVERSATION SUMMARY", compressed[0].content)

    def test_hybrid_retriever_and_rrf(self):
        doc1 = Document(
            page_content="Distributed consensus algorithms like Raft and Paxos ensure cluster consistency.",
            metadata={"filename": "consensus.pdf", "page": 2, "chunk_id": "c1"},
        )
        doc2 = Document(
            page_content="Vector databases index embeddings for nearest neighbor retrieval using HNSW graphs.",
            metadata={"filename": "vectors.pdf", "page": 5, "chunk_id": "c2"},
        )

        class MockVectorStore:
            def max_marginal_relevance_search(self, query, k=5, fetch_k=10):
                return [doc2, doc1]

        retriever = HybridRetriever(vector_store=MockVectorStore(), all_documents=[doc1, doc2])
        results = retriever.retrieve("Raft consensus algorithm", k=2)

        self.assertGreaterEqual(len(results), 1)
        self.assertIn("citation", results[0])
        self.assertIn("score", results[0])
        # doc1 should rank high because of strong keyword match
        self.assertEqual(results[0]["source"], "consensus.pdf")

    def test_multi_doc_manager_and_rag_tool(self):
        tid = "multi-doc-thread-test"

        # Ingest Document 1 (TXT)
        doc1_bytes = b"Revenue for Q3 reached $14.2M with 35% growth year over year."
        sum1 = ingest_pdf(doc1_bytes, thread_id=tid, filename="financials_q3.txt")
        self.assertEqual(sum1["filename"], "financials_q3.txt")

        # Ingest Document 2 (Markdown)
        doc2_bytes = b"# Engineering Roadmap\nPhase 3 delivers long term memory and hybrid search."
        sum2 = ingest_pdf(doc2_bytes, thread_id=tid, filename="roadmap.md")
        self.assertEqual(sum2["filename"], "roadmap.md")

        # Multi-document registry
        docs = multi_doc_manager.get_documents(tid)
        self.assertEqual(len(docs), 2)
        filenames = [d["filename"] for d in docs]
        self.assertIn("financials_q3.txt", filenames)
        self.assertIn("roadmap.md", filenames)

        # Call rag_tool
        rag_res = rag_tool.invoke({"query": "What is the engineering roadmap?", "thread_id": tid})
        self.assertNotIn("error", rag_res)
        self.assertIn("citations", rag_res)
        self.assertIn("scores", rag_res)
        self.assertGreaterEqual(len(rag_res["context"]), 1)

        # Cleanup
        multi_doc_manager.remove_thread(tid)
        self.assertFalse(multi_doc_manager.has_documents(tid))

    def test_planner_and_goal_reflection(self):
        # 1. Create plan
        plan = create_plan.invoke({
            "goal": "Conduct market research and compile pricing comparison",
            "steps": ["Search current competitor pricing", "Analyze tier features", "Generate report"],
        })
        self.assertIn("plan_id", plan)
        self.assertEqual(plan["total_steps"], 3)
        self.assertEqual(plan["status"], "in_progress")
        pid = plan["plan_id"]

        # 2. Update step
        updated = update_plan_step.invoke({
            "plan_id": pid,
            "step_number": 1,
            "status": "completed",
            "result_summary": "Found competitor plans from $29/mo to $99/mo.",
        })
        self.assertEqual(updated["completed_steps"], 1)

        # 3. Reflect on goal
        reflection = reflect_on_goal.invoke({
            "goal": "Conduct market research and compile pricing comparison",
            "observations": ["Competitor A charges $49/mo with 5 seats; Competitor B charges $99/mo unlimited."],
            "completed_steps": ["Search current competitor pricing"],
        })
        self.assertTrue(reflection["goal_completed"])
        self.assertIn("Formulate", reflection["next_action"])


if __name__ == "__main__":
    unittest.main()
