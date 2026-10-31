"""Typed exceptions and HTTP error mappings for DeepSeek Harness."""
from __future__ import annotations


class HarnessError(Exception):
    """Base class for all DeepSeek Harness errors."""

    def __init__(self, message: str, status_code: int = 500, error_code: str = "HARNESS_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


class RuntimeUnavailable(HarnessError):
    """Raised when harness runtime cannot be launched, initialized, or reached."""

    def __init__(self, message: str = "Harness runtime is currently unavailable."):
        super().__init__(message, status_code=503, error_code="RUNTIME_UNAVAILABLE")


class SessionBusy(HarnessError):
    """Raised when a concurrent request targets an already active session."""

    def __init__(self, message: str = "Session is currently processing another turn."):
        super().__init__(message, status_code=409, error_code="SESSION_BUSY")


class ProtocolError(HarnessError):
    """Raised when communication protocol violation or invalid response occurs."""

    def __init__(self, message: str = "Harness JSON-RPC protocol error."):
        super().__init__(message, status_code=502, error_code="PROTOCOL_ERROR")


class QuotaExceeded(HarnessError):
    """Raised when tenant exceeds turn quota, concurrent turns, or tool call limit."""

    def __init__(self, message: str = "Harness resource quota exceeded."):
        super().__init__(message, status_code=429, error_code="QUOTA_EXCEEDED")

