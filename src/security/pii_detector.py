"""PII (Personally Identifiable Information) Detection and Masking Engine.

Identifies sensitive personal information (emails, phone numbers, credit cards,
SSNs, API keys/secrets, IP addresses) and provides redaction and tokenization.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import tool


@dataclass
class PIIMatch:
    pii_type: str
    original: str
    start: int
    end: int
    masked: str


class PIIDetector:
    """Detects and masks personally identifiable information in texts."""

    PATTERNS = {
        "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "PHONE": r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
        "CREDIT_CARD": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        "IPV4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "API_KEY": r"(?:api[_-]?key|secret|token|password|bearer)[\s:=]+['\"]?([A-Za-z0-9_\-]{16,})['\"]?",
    }

    def detect_pii(self, text: str) -> list[PIIMatch]:
        """Scan text and return all detected PII occurrences."""
        matches: list[PIIMatch] = []
        for pii_type, pattern in self.PATTERNS.items():
            for m in re.finditer(pattern, text, re.IGNORECASE):
                val = m.group(1) if (pii_type == "API_KEY" and m.groups()) else m.group(0)
                start, end = (m.start(1), m.end(1)) if (pii_type == "API_KEY" and m.groups()) else (m.start(), m.end())
                masked = self._mask_value(val, pii_type)
                matches.append(PIIMatch(pii_type=pii_type, original=val, start=start, end=end, masked=masked))
        # Sort by start position
        matches.sort(key=lambda x: x.start)
        return matches

    def _mask_value(self, val: str, pii_type: str) -> str:
        """Create a safe masked representation of a sensitive value."""
        if pii_type == "EMAIL":
            parts = val.split("@")
            user = parts[0]
            domain = parts[1] if len(parts) > 1 else ""
            masked_user = user[0] + "***" if len(user) > 1 else "***"
            return f"{masked_user}@{domain}"
        if pii_type == "CREDIT_CARD":
            clean = re.sub(r"\D", "", val)
            return f"****-****-****-{clean[-4:]}" if len(clean) >= 4 else "****"
        if pii_type == "SSN":
            return "***-**-" + val.split("-")[-1]
        if pii_type == "PHONE":
            digits = re.sub(r"\D", "", val)
            return f"***-***-{digits[-4:]}" if len(digits) >= 4 else "***-***-****"
        if pii_type == "API_KEY":
            return f"[REDACTED_API_KEY_{len(val)}ch]"
        return f"[REDACTED_{pii_type}]"

    def mask_text(self, text: str) -> dict[str, Any]:
        """Redact all detected PII in text and return sanitized version."""
        matches = self.detect_pii(text)
        if not matches:
            return {"sanitized_text": text, "pii_detected": False, "detected_count": 0, "pii_types": []}

        # Replace from end to start to preserve slice offsets
        sanitized = text
        for match in sorted(matches, key=lambda x: x.start, reverse=True):
            sanitized = sanitized[:match.start] + match.masked + sanitized[match.end:]

        pii_types = sorted(list({m.pii_type for m in matches}))
        return {
            "sanitized_text": sanitized,
            "pii_detected": True,
            "detected_count": len(matches),
            "pii_types": pii_types,
        }


pii_detector = PIIDetector()


@tool
def scan_and_mask_pii(text: str) -> dict[str, Any]:
    """Scan input text for sensitive Personally Identifiable Information (PII) and return masked content.

    Args:
        text: The text to inspect and redact.
    """
    return pii_detector.mask_text(text)
