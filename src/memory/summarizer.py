"""Conversation history summarizer and context compression.

Compresses older turns into a compact summary message when the message history
exceeds the context window threshold, preserving key facts while saving tokens.
"""
from __future__ import annotations

import re
from typing import Sequence
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


def extract_key_points(text: str, max_points: int = 3) -> list[str]:
    """Extract key declarative statements from text using sentence chunking."""
    sentences = re.split(r"[.!?]\s+", text.strip())
    meaningful = [
        s.strip()
        for s in sentences
        if len(s.strip()) > 15 and not s.strip().startswith(("Hi", "Hello", "Hey", "Thanks"))
    ]
    return meaningful[:max_points]


def summarize_conversation_messages(
    messages: Sequence[BaseMessage],
    threshold: int = 10,
    keep_recent: int = 6,
) -> list[BaseMessage]:
    """Compress conversation messages if length exceeds threshold.

    Retains the most recent `keep_recent` messages verbatim, while
    compressing older messages into a single SystemMessage summary at the top.
    """
    if len(messages) <= threshold:
        return list(messages)

    to_summarize = messages[:-keep_recent]
    recent_messages = list(messages[-keep_recent:])

    summary_bullets: list[str] = []
    for msg in to_summarize:
        role = getattr(msg, "type", "message")
        content = str(getattr(msg, "content", ""))
        if not content:
            continue

        if role == "human":
            summary_bullets.append(f"User inquired: {content[:150]}")
        elif role == "ai":
            points = extract_key_points(content, max_points=2)
            if points:
                summary_bullets.append(f"Assistant noted: {'; '.join(points)}")
            else:
                summary_bullets.append(f"Assistant answered: {content[:120]}")

    summary_text = (
        "[PREVIOUS CONVERSATION SUMMARY]\n"
        + ("\n".join(f"- {b}" for b in summary_bullets) if summary_bullets else "Prior discussion took place.")
        + "\n[END SUMMARY — Resuming verbatim conversation below]"
    )

    return [SystemMessage(content=summary_text), *recent_messages]
