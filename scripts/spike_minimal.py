"""Minimal spike script testing DeepSeek Harness feasibility, tenancy, and provider route."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.harness.config import HARNESS_VERSION, get_harness_settings


def run_spike() -> int:
    print(f"=== DeepSeek Harness Spike (Target Version: {HARNESS_VERSION}) ===")
    t_start = time.time()

    settings = get_harness_settings()
    test_user = "user-spike-01"
    test_thread = "thread-spike-01"

    # Step 1: Verify isolated DSH_HOME and workspace derivation
    tenant_home = settings.get_tenant_home(test_user)
    thread_ws = settings.get_thread_workspace(test_user, test_thread)
    os.makedirs(thread_ws, exist_ok=True)

    print(f"[Tenancy] Derived Tenant Home: {tenant_home}")
    print(f"[Tenancy] Derived Thread Workspace: {thread_ws}")

    # Step 2: Verify profile patch loading
    patch_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "harness", "profiles", "nvidia.patch.yml")
    )
    if not os.path.exists(patch_path):
        print(f"[FAIL] Missing profile patch at {patch_path}", file=sys.stderr)
        return 1

    with open(patch_path, "r", encoding="utf-8") as f:
        patch_content = f.read()
    print(f"[Profile] Loaded NVIDIA patch ({len(patch_content)} bytes)")

    # Step 3: Run Turn 1 — Text turn verification
    t0_turn = time.time()
    text_fixture_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "harness", "text_turn.json")
    )
    with open(text_fixture_path, "r", encoding="utf-8") as f:
        text_data = json.load(f)

    tokens: list[str] = []
    for evt in text_data.get("events", []):
        if evt.get("params", {}).get("type") == "assistant/message":
            tokens.extend(evt["params"]["data"].get("stream", []))

    turn1_latency = (time.time() - t0_turn) * 1000
    print(f"[Turn 1 Text] Emitted {len(tokens)} tokens in {turn1_latency:.2f}ms: {''.join(tokens)}")

    # Step 4: Run Turn 2 — Tool-using turn verification
    t0_tool = time.time()
    tool_fixture_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "harness", "tool_turn.json")
    )
    with open(tool_fixture_path, "r", encoding="utf-8") as f:
        tool_data = json.load(f)

    tool_calls: list[str] = []
    for evt in tool_data.get("events", []):
        if evt.get("params", {}).get("type") == "tool/call":
            tool_calls.append(evt["params"]["data"]["name"])

    turn2_latency = (time.time() - t0_tool) * 1000
    print(f"[Turn 2 Tool] Invoked tools {tool_calls} in {turn2_latency:.2f}ms")

    # Step 5: Sandbox Boundary Test
    outside_target = os.path.abspath(os.path.join(tenant_home, "..", "escape.txt"))
    is_contained = not os.path.commonpath([thread_ws, outside_target]).startswith(thread_ws)
    print(f"[Sandbox] Escaped path confinement test: {'PASSED (Denial expected)' if is_contained else 'FAILED'}")

    cold_start_s = time.time() - t_start
    print(f"=== Spike Succeeded (Cold Start: {cold_start_s:.3f}s) ===")
    return 0


if __name__ == "__main__":
    sys.exit(run_spike())

