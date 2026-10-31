# ADR-001: DeepSeek Harness as Alternative Chat Backend

- **Status**: Accepted
- **Deciders**: Agent-Pilot Core Architecture Team
- **Date**: 2026-10-31

## Context

Agent-Pilot currently executes agentic workflows via LangGraph (`langraph_rag_backend.py`). To enable support for the DeepSeek Harness ecosystem (`@deepseek-ai/dsh` / `deepseek-harness-sdk`), provide advanced sandboxing, plugin-driven modularity, and reproducible execution environments, we require an opt-in integration that coexists with the LangGraph runtime without disrupting existing deployments.

## Decision

We will integrate DeepSeek Harness into Agent-Pilot behind an environment-driven strategy pattern:
1. `AGENT_BACKEND` defaults to `langgraph`. Setting `AGENT_BACKEND=harness` activates the `HarnessBackend`. `AGENT_BACKEND=shadow` runs both for telemetry comparison.
2. Runtime isolation will enforce one `DSH_HOME` and separate process per tenant. Tenants paths are salted via HMAC-SHA256.
3. Client API and SSE streaming contracts are frozen (`POST /api/chat`, `POST /api/chat/stream`). Event signatures (`token`, `tool`, `done`, `error`) remain strictly identical.
4. Tool execution will be routed over an internal loopback MCP server (`POST /mcp`) secured by `MCP_INTERNAL_TOKEN`. The harness has no direct database or host filesystem access.
5. All sensitive mutations must pass through the `HITLManager` approval bridge and fail closed.
6. Database persistence will be purely additive (`harness_sessions`, `harness_events`, `harness_approvals`), maintaining zero-downtime rollback capability.

## Consequences

### Positive
- High-efficiency agent execution with modular profile configurations.
- Sandboxed workspace isolation per tenant and session.
- Complete backward compatibility: immediate fallback to LangGraph on runtime failure.
- No client-side breaking changes.

### Negative / Trade-offs
- Additional runtime supervisor complexity (process lifecycle, eviction, health checks).
- Requires local node runtime or wheel-embedded binary for `dsh`.
- Additional database tables and event sync logic.
