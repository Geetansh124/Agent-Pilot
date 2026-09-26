"""Self-evaluation and critic loop.

Evaluates assistant responses against source context for factual groundedness,
hallucination risk, citation completeness, and overall answer fidelity.
"""
from __future__ import annotations

import re
from typing import Any
from langchain_core.tools import tool


class CriticAgent:
    """Evaluates response fidelity, grounding, and hallucination risk."""

    def evaluate(
        self, question: str, context: str, response: str
    ) -> dict[str, Any]:
        """Critique an assistant answer against retrieved source context."""
        clean_resp = response.strip()
        clean_ctx = context.strip()
        clean_q = question.strip()

        critique_notes: list[str] = []
        deductions = 0.0

        if not clean_resp:
            return {
                "score": 0.0,
                "is_acceptable": False,
                "hallucination_detected": False,
                "critique_notes": ["Response is empty."],
            }

        # 1. Check citation presence if context is provided
        has_citations = bool(re.search(r"\[.*?(page|section|doc|chunk|http).*?\]", clean_resp, re.IGNORECASE))
        if clean_ctx and not has_citations:
            deductions += 0.2
            critique_notes.append("No source citations detected in document-grounded response.")

        # 2. Check token grounding / potential hallucination
        resp_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", clean_resp.lower()))
        ctx_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", clean_ctx.lower()))
        hallucination_detected = False

        if clean_ctx and resp_words:
            overlap = len(resp_words.intersection(ctx_words))
            overlap_ratio = overlap / len(resp_words)
            if overlap_ratio < 0.15:
                deductions += 0.4
                hallucination_detected = True
                critique_notes.append("Low factual overlap with context (potential hallucination).")
            elif overlap_ratio < 0.35:
                deductions += 0.15
                critique_notes.append("Moderate factual overlap with source context.")

        # 3. Check question responsiveness
        q_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", clean_q.lower()))
        if q_words and not any(w in resp_words for w in q_words):
            deductions += 0.2
            critique_notes.append("Response does not echo key terms from user question.")

        score = max(0.0, round(1.0 - deductions, 2))
        is_acceptable = score >= 0.65 and not hallucination_detected

        if is_acceptable and not critique_notes:
            critique_notes.append("Response is well-grounded, responsive, and properly cited.")

        return {
            "score": score,
            "is_acceptable": is_acceptable,
            "hallucination_detected": hallucination_detected,
            "critique_notes": critique_notes,
        }


critic_agent = CriticAgent()


@tool
def evaluate_response(question: str, context: str, response: str) -> dict[str, Any]:
    """Evaluate an assistant response for factual grounding, citations, and hallucination risk.

    Args:
        question: The original user question.
        context: The source reference text or document context.
        response: The candidate assistant response to evaluate.
    """
    return critic_agent.evaluate(question=question, context=context, response=response)
