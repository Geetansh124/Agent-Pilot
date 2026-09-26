"""Security guardrails, prompt injection detection, and data leakage protection.

Scans inputs for adversarial jailbreaks and prompt injection patterns,
and scrubs sensitive credentials/PII from agent outputs.
"""
from __future__ import annotations

import re
from typing import Tuple

# Common prompt injection and jailbreak signatures
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|directives|prompts)",
    r"disregard\s+(all\s+)?(previous|prior)\s+(instructions|rules)",
    r"(reveal|print|show|dump|output)\s+(the\s+)?(system|initial)\s+(prompt|instructions)",
    r"you\s+are\s+now\s+(in\s+)?(dan|jailbreak|developer|unrestricted)\s+mode",
    r"act\s+as\s+(an\s+)?unrestricted\s+ai",
    r"bypass\s+(all\s+)?(safety|content|ethical)\s+(filters|rules|guidelines)",
    r"do\s+anything\s+now\s+mode",
    r"forget\s+all\s+(your\s+)?guidelines",
]

# Sensitive credentials & PII patterns to redact from outputs
SECRET_PATTERNS = [
    (r"\b(nvapi-[A-Za-z0-9_-]{30,})\b", "[REDACTED_API_KEY]"),
    (r"\b(sk-[A-Za-z0-9]{32,})\b", "[REDACTED_API_KEY]"),
    (r"\b(ghp_[A-Za-z0-9]{36,})\b", "[REDACTED_GITHUB_TOKEN]"),
    (r"\b(Bearer\s+ey[A-Za-z0-9._-]{20,})\b", "Bearer [REDACTED_TOKEN]"),
    (r"\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7})\b", "[REDACTED_EMAIL]"),
    (r"\b(\d{3}-\d{2}-\d{4})\b", "[REDACTED_SSN]"),
    (r"\b(?:\d{4}[ -]?){3}\d{4}\b", "[REDACTED_CARD]"),
]


def detect_prompt_injection(text: str) -> Tuple[bool, str]:
    """Scan text for known prompt injection and jailbreak attempts.

    Returns:
        (is_injection, reason)
    """
    clean = text.lower()
    for pattern in INJECTION_PATTERNS:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            return True, f"Prompt injection signature detected: '{match.group(0)}'"

    # Check for excessive delimiter abuse (e.g., repeated markdown system tags)
    if clean.count("<system>") > 1 or clean.count("[system]") > 1:
        return True, "Potential delimiter manipulation detected."

    return False, ""


def validate_input_prompt(text: str) -> Tuple[bool, str]:
    """Validate user prompt at system boundaries.

    Ensures prompt meets size limits and does not trigger injection signatures.
    """
    if not text.strip():
        return False, "Prompt cannot be empty."

    if len(text) > 20000:
        return False, "Prompt exceeds maximum allowed length of 20,000 characters."

    is_injection, reason = detect_prompt_injection(text)
    if is_injection:
        return False, reason

    return True, ""


def sanitize_output(text: str) -> str:
    """Scrub leaked API credentials, keys, and PII from assistant output."""
    sanitized = text
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized)
    return sanitized
