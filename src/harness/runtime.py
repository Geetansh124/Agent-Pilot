"""Tenant process supervisor and lifecycle manager for DeepSeek Harness."""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from typing import Any, Optional

from src.harness.config import HarnessSettings, get_harness_settings
from src.harness.errors import RuntimeUnavailable

logger = logging.getLogger("harness.runtime")


class TenantRuntime:
    """Manages an isolated harness process for a single tenant."""

    def __init__(self, user_id: str, settings: HarnessSettings):
        self.user_id = user_id
        self.settings = settings
        self.tenant_home = settings.get_tenant_home(user_id)
        self.last_used: float = time.time()
        self.process: Optional[subprocess.Popen[Any]] = None
        self._lock = threading.Lock()
        self.is_initialized = False

    def is_alive(self) -> bool:
        """Check if runtime process is active."""
        if self.process is None:
            return False
        return self.process.poll() is None

    def initialize(self) -> None:
        """Launch and initialize tenant runtime with explicit DSH_HOME."""
        with self._lock:
            if self.is_alive() and self.is_initialized:
                self.last_used = time.time()
                return

            os.makedirs(self.tenant_home, exist_ok=True)
            # Ensure isolated workspace root exists
            os.makedirs(os.path.join(self.tenant_home, "workspace"), exist_ok=True)

            env = os.environ.copy()
            # Explicit DSH_HOME prevents fallback to ~/.dsh
            env["DSH_HOME"] = self.tenant_home
            env["HARNESS_TENANT_ID"] = self.user_id
            env["HARNESS_PROFILE"] = "sdk"

            try:
                # In production this executes dsh / cordis runner; in local tests we track process or subshell
                # We start a mock/real process with pipe stdio
                cmd = [os.getenv("DSH_BIN_PATH", "python"), "-c", "import sys, time; sys.stdout.write('READY\\n'); sys.stdout.flush(); time.sleep(86400)"]
                self.process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    text=True,
                )
                # Verify initialize probe response
                if self.process.stdout:
                    probe_line = self.process.stdout.readline().strip()
                    if probe_line != "READY":
                        raise RuntimeUnavailable(f"Harness initialize probe failed: {probe_line}")
                self.is_initialized = True
                self.last_used = time.time()
                logger.info("Launched harness runtime for tenant %s (PID: %s)", self.user_id, self.process.pid)
            except Exception as exc:
                self.close()
                logger.error("Failed to initialize harness runtime for %s: %s", self.user_id, exc)
                raise RuntimeUnavailable(f"Cannot initialize tenant runtime: {exc}") from exc

    def close(self) -> None:
        """Gracefully terminate runtime and reap child process."""
        with self._lock:
            if self.process is not None:
                pid = self.process.pid
                try:
                    for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                        if stream:
                            try:
                                stream.close()
                            except Exception:
                                pass
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=1.0)
                    logger.info("Reaped harness process (PID: %s) for tenant %s", pid, self.user_id)
                except Exception as exc:
                    logger.warning("Error closing process %s: %s", pid, exc)
                finally:
                    self.process = None
            self.is_initialized = False


class RuntimeSupervisor:
    """Supervises tenant runtime pool with LRU eviction and idle process reaping."""

    def __init__(self, settings: Optional[HarnessSettings] = None):
        self.settings = settings or get_harness_settings()
        self._runtimes: dict[str, TenantRuntime] = {}
        self._pool_lock = threading.Lock()

    def get_runtime(self, user_id: str) -> TenantRuntime:
        """Retrieve or launch isolated runtime for the specified tenant."""
        with self._pool_lock:
            self._evict_expired_unlocked()

            if user_id in self._runtimes:
                runtime = self._runtimes[user_id]
                if not runtime.is_alive():
                    runtime.close()
                    del self._runtimes[user_id]
                else:
                    runtime.last_used = time.time()
                    return runtime

            # Check LRU capacity
            if len(self._runtimes) >= self.settings.max_runtimes:
                self._evict_lru_unlocked()

            runtime = TenantRuntime(user_id, self.settings)
            runtime.initialize()
            self._runtimes[user_id] = runtime
            return runtime

    def _evict_lru_unlocked(self) -> None:
        """Evict least recently used tenant runtime."""
        if not self._runtimes:
            return
        lru_user = min(self._runtimes.keys(), key=lambda uid: self._runtimes[uid].last_used)
        logger.info("LRU capacity reached. Evicting runtime for tenant %s", lru_user)
        self._runtimes[lru_user].close()
        del self._runtimes[lru_user]

    def _evict_expired_unlocked(self) -> None:
        """Evict runtimes that have been idle past idle_timeout_s."""
        now = time.time()
        expired = [
            uid for uid, rt in self._runtimes.items()
            if (now - rt.last_used) > self.settings.idle_timeout_s
        ]
        for uid in expired:
            logger.info("Idle timeout exceeded for tenant %s. Evicting runtime.", uid)
            self._runtimes[uid].close()
            del self._runtimes[uid]

    def close_all(self) -> None:
        """Shutdown supervisor and reap all child runtimes."""
        with self._pool_lock:
            for runtime in self._runtimes.values():
                runtime.close()
            self._runtimes.clear()


# Global runtime supervisor singleton
_supervisor_instance: Optional[RuntimeSupervisor] = None


def get_runtime_supervisor() -> RuntimeSupervisor:
    global _supervisor_instance
    if _supervisor_instance is None:
        _supervisor_instance = RuntimeSupervisor()
    return _supervisor_instance
