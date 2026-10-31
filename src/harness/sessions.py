"""Session mapping, tenancy verification, and per-session concurrency controls."""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Generator, Optional

from src.harness.config import HarnessSettings, get_harness_settings
from src.harness.errors import SessionBusy


class SessionMapper:
    """Manages thread-to-harness session mapping, locks, and workspace paths."""

    def __init__(self, settings: Optional[HarnessSettings] = None):
        self.settings = settings or get_harness_settings()
        self._locks: dict[tuple[str, str], threading.Lock] = {}
        self._global_lock = threading.Lock()

    @staticmethod
    def get_harness_session_id(thread_id: str) -> str:
        """Derive standard harness session ID from Agent-Pilot thread ID."""
        return f"ap-{thread_id}"

    def get_workspace_path(self, user_id: str, thread_id: str) -> str:
        """Return canonical workspace root for this tenant and thread."""
        path = self.settings.get_thread_workspace(user_id, thread_id)
        os.makedirs(path, exist_ok=True)
        return path

    @contextmanager
    def acquire_session_lock(
        self, user_id: str, thread_id: str, timeout: float = 0.1
    ) -> Generator[None, None, None]:
        """Acquire per-(tenant, session) turn execution lock.
        
        Raises SessionBusy if another turn is actively running on this session.
        Different sessions for the same or different tenants may execute concurrently.
        """
        key = (user_id, thread_id)
        with self._global_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            lock = self._locks[key]

        acquired = lock.acquire(timeout=timeout)
        if not acquired:
            raise SessionBusy(f"Thread '{thread_id}' is already processing an active turn.")
        try:
            yield
        finally:
            lock.release()


_mapper_instance: Optional[SessionMapper] = None


def get_session_mapper() -> SessionMapper:
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = SessionMapper()
    return _mapper_instance

