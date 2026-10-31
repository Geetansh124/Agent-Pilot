"""Configuration and tenancy path policies for DeepSeek Harness integration."""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field
from typing import Literal

# Exact pinned harness ecosystem version
HARNESS_VERSION = "0.2.2-alpha.2"


@dataclass
class HarnessSettings:
    """Settings controlling DeepSeek Harness runtime, tenancy, and quotas."""

    backend: Literal["langgraph", "harness", "shadow"] = "langgraph"
    home_root: str = field(
        default_factory=lambda: os.getenv(
            "HARNESS_HOME_ROOT",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "harness")),
        )
    )
    path_salt: str = field(
        default_factory=lambda: os.getenv("HARNESS_PATH_SALT", "ap-harness-default-salt-v1")
    )
    mcp_internal_token: str = field(
        default_factory=lambda: os.getenv("MCP_INTERNAL_TOKEN", "ap-internal-mcp-bearer-token")
    )
    provider: str = field(
        default_factory=lambda: os.getenv("HARNESS_PROVIDER", "nvidia")
    )
    model: str = field(
        default_factory=lambda: os.getenv("HARNESS_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
    )
    max_runtimes: int = 10
    idle_timeout_s: int = 300
    turn_timeout_s: int = 120
    max_concurrent_turns: int = 20
    max_tool_calls: int = 30

    @classmethod
    def from_env(cls) -> HarnessSettings:
        raw_backend = os.getenv("AGENT_BACKEND", "langgraph").strip().lower()
        backend_val: Literal["langgraph", "harness", "shadow"]
        if raw_backend in ("harness", "shadow"):
            backend_val = raw_backend  # type: ignore[assignment]
        else:
            backend_val = "langgraph"

        return cls(
            backend=backend_val,
            max_runtimes=int(os.getenv("HARNESS_MAX_RUNTIMES", "10")),
            idle_timeout_s=int(os.getenv("HARNESS_IDLE_TIMEOUT_S", "300")),
            turn_timeout_s=int(os.getenv("HARNESS_TURN_TIMEOUT_S", "120")),
            max_concurrent_turns=int(os.getenv("HARNESS_MAX_CONCURRENT_TURNS", "20")),
            max_tool_calls=int(os.getenv("HARNESS_MAX_TOOL_CALLS", "30")),
        )

    def get_tenant_hash(self, user_id: str) -> str:
        """Derive reproducible HMAC-SHA256 salted hash for tenant isolation."""
        return hmac.new(
            self.path_salt.encode("utf-8"),
            user_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def get_tenant_home(self, user_id: str) -> str:
        """Resolve isolated DSH_HOME for tenant."""
        tenant_hash = self.get_tenant_hash(user_id)
        return os.path.abspath(os.path.join(self.home_root, tenant_hash, "home"))

    def get_thread_workspace(self, user_id: str, thread_id: str) -> str:
        """Resolve sandboxed workspace for thread under tenant home."""
        tenant_home = self.get_tenant_home(user_id)
        # Prevent path traversal in thread_id
        safe_thread_id = os.path.basename(thread_id).strip()
        if not safe_thread_id or ".." in thread_id:
            safe_thread_id = "default"
        return os.path.abspath(os.path.join(tenant_home, "workspace", safe_thread_id))


_settings_instance: HarnessSettings | None = None


def get_harness_settings() -> HarnessSettings:
    """Return singleton instance of HarnessSettings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = HarnessSettings.from_env()
    return _settings_instance


def reset_harness_settings() -> None:
    """Reset cached settings instance (useful for unit tests)."""
    global _settings_instance
    _settings_instance = None

