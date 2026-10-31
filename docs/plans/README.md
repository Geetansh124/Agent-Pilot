# DeepSeek Harness Integration for Agent-Pilot

## 1. Executive Summary

This directory documents the integration of the **DeepSeek Harness** (`dsh`) into the Agent-Pilot multi-tenant architecture as an alternative, production-grade agent execution engine alongside the existing LangGraph backend.

The integration provides:
- **Pluggable Agent Backend**: Seamless switching between `AGENT_BACKEND=langgraph` and `AGENT_BACKEND=harness` via an environment variable.
- **Tenant Isolation**: Strict per-tenant workspace, runtime process isolation (`DSH_HOME`), and salted path policies preventing cross-tenant leakage.
- **Client & SSE Parity**: Complete preservation of the existing `POST /api/chat` and `POST /api/chat/stream` contract, auth mechanisms, and UI behavior.
- **Internal Authenticated MCP Bridge**: Access to Agent-Pilot's tools (RAG, web search, database querying, file tools) over an authenticated loopback Model Context Protocol (MCP) HTTP interface.
- **Human-in-the-Loop (HITL) Gate**: Fail-closed approval bridge integrated with Agent-Pilot's `HITLManager`.

## 2. Document Navigation

- [Architecture & Design Plan](deepseek-harness-integration-plan.md) — Normative architecture, tenancy, module design, data model, and phase roadmap (§4, §5, §6, §8).
- [ADR-001: Harness Integration](adr-001-harness-integration.md) — Architectural Decision Record, context, consequences, and alternatives.
- [Ticket Inventory](deepseek-harness-integration-tickets.md) — Comprehensive tickets (`HP-001` through `HP-085`) grouped by phase.
- [Implementation Log](implementation-log.md) — Living progress log, baseline commit, version pins, and phase gate audit evidence.

## 3. Scope & Recommendation

Integration proceeds in 9 defined phases (Phase 0 through Phase 8), beginning with a self-contained feasibility gate and progressing through supervisor tenancy, SSE chat bridge, MCP bridge, approvals, persistence sync, live streaming, observability/quotas, and hardening.
