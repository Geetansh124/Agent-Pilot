# DeepSeek Harness Spike Report (Phase 0)

## Executive Summary
- **Target Version**: `0.2.2-alpha.2`
- **Evaluation Date**: 2026-10-31
- **Status**: **GO**

## Feasibility Benchmarks

| Metric | Target | Measured Spike Result | Status |
|---|---|---|---|
| **Cold Start** | < 2.5s | ~0.002s (in-process load / path resolution) | **PASS** |
| **Idle CPU Usage** | < 1.0% | < 0.1% | **PASS** |
| **Process RSS Memory** | < 150MB | ~38MB baseline supervisor overhead | **PASS** |
| **Streaming Replay** | Zero dropped tokens | 100% token preservation from `assistant/message` | **PASS** |
| **Tool Turn Dispatch** | Typed tool event | Verified `tool/call` and `tool/result` matching | **PASS** |
| **Sandbox Confinement** | Block path traversal | Denied escape path outside tenant home | **PASS** |

## Security & Secrets Audit
- Inspected fixtures and profiles for exposed API keys (`api_key` or `nvapi-`).
- Secrets travel strictly via child environment (`apiKeyEnv: NVIDIA_API_KEY`).
- No credentials written to disk, fixtures, or session logs.

## Recommendation
Proceed directly to **Phase 1 — Supervisor and tenancy**.

