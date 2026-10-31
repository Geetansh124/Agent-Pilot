# DeepSeek Harness Integration — Ticket Inventory

## Phase 0: Feasibility & Foundation (HP-001 … HP-006)
- **HP-001**: Pinned dependency specification & runtime environment check (`src/harness/config.py`).
- **HP-002**: Minimal spike runner script (`scripts/spike_minimal.py`).
- **HP-003**: Provider profile patch definition (`harness/profiles/nvidia.patch.yml`).
- **HP-004**: Harness event and status test fixtures (`tests/fixtures/harness/`).
- **HP-005**: Sandbox path confinement test & verification evidence (`tests/fixtures/harness/sandbox.md`).
- **HP-006**: Phase 0 feasibility evaluation & spike report (`docs/plans/spike-report.md`).

## Phase 1: Supervisor & Tenancy (HP-010 … HP-015)
- **HP-010**: Typed exception hierarchy (`src/harness/errors.py`).
- **HP-011**: Configuration & salted path policies (`src/harness/config.py`).
- **HP-012**: Runtime supervisor & process lifecycle manager (`src/harness/runtime.py`).
- **HP-013**: Session mapper & tenant thread workspace scoping (`src/harness/sessions.py`).
- **HP-014**: Database migration for `harness_sessions` table (`src/auth/database.py`).
- **HP-015**: Unit tests for supervisor, eviction, and isolation (`tests/test_harness_supervisor.py`).

## Phase 2: Chat Backend & SSE (HP-020 … HP-025)
- **HP-020**: Event translation from harness notifications to Agent-Pilot SSE format (`src/harness/translate.py`).
- **HP-021**: Implementation of `HarnessBackend` class adhering to chat protocol (`src/harness/backend.py`).
- **HP-022**: Wire communication layer for stdio JSON-RPC transport (`src/harness/wire.py`).
- **HP-023**: Dynamic backend router with LangGraph fallback (`src/harness/router.py`).
- **HP-024**: Integration of backend router into `api_server.py` (`/api/chat` and `/api/chat/stream`).
- **HP-025**: Unit & integration tests for SSE stream preservation (`tests/test_harness_chat.py`).

## Phase 3: Authenticated MCP Bridge & Tools (HP-030 … HP-034)
- **HP-030**: Bearer token authentication and constant-time check for MCP server (`src/mcp/mcp_server.py`).
- **HP-031**: Agent-Pilot internal tool registration for MCP (RAG, web search, database, files).
- **HP-032**: Profile patch for Agent-Pilot MCP client connection (`harness/profiles/ap-tools.patch.yml`).
- **HP-033**: Server-side tenant scoping for MCP tool invocations.
- **HP-034**: Tests for MCP auth, tool dispatch, and cross-tenant rejection (`tests/test_harness_mcp.py`).

## Phase 4: Approvals & HITL Integration (HP-040 … HP-044)
- **HP-040**: Harness approval bridge integrating with `HITLManager` (`src/harness/approvals.py`).
- **HP-041**: API endpoints for approval listing and decision submission in `api_server.py`.
- **HP-042**: Question and answer negotiation endpoint for agent prompts.
- **HP-043**: Frontend approval dialog modal component (`frontend/app/components/ApprovalModal.tsx`).
- **HP-044**: Tests for fail-closed approvals, expiration, and user validation (`tests/test_harness_approvals.py`).

## Phase 5: Persistence, State Sync & Projections (HP-050 … HP-055)
- **HP-050**: Additive SQLite tables `harness_events` and `harness_approvals` in `src/auth/database.py`.
- **HP-051**: Event append and projection store to `messages` (`src/harness/store.py`).
- **HP-052**: JSONL session state sync with remote storage (`src/harness/sync.py`).
- **HP-053**: Session restore verification and SHA-256 integrity checks.
- **HP-054**: Reconciliation utility script (`scripts/harness_reconcile.py`).
- **HP-055**: Crash recovery and idempotent playback tests (`tests/test_harness_persistence.py`).

## Phase 6: Live Streaming & Shadow Evaluation (HP-060 … HP-064)
- **HP-060**: Stream forwarder plugin definition (`harness/plugins/stream-forwarder/`).
- **HP-061**: Wire layer extensions for real-time delta consumption.
- **HP-062**: Safe fallback to message chunk replay when forwarder is absent.
- **HP-063**: Shadow execution mode in `src/harness/router.py`.
- **HP-064**: Shadow comparison metrics and parity verification tests.

## Phase 7: Observability, Metrics & Quota Controls (HP-070 … HP-074)
- **HP-070**: Structured audit events for harness operations in `src/harness/metrics.py`.
- **HP-071**: Per-tenant token and cost accounting.
- **HP-072**: Concurrency and turn quota enforcement (`HARNESS_MAX_CONCURRENT_TURNS`).
- **HP-073**: Admin metrics summary endpoint in `api_server.py`.
- **HP-074**: Quota limit and rate-limiting test suite (`tests/test_harness_quotas.py`).

## Phase 8: Hardening, Chaos Matrix & Rollout (HP-080 … HP-085)
- **HP-080**: Chaos resilience tests (process kill, corrupted tail, delayed approval).
- **HP-081**: Security audit against path traversal and prompt leakage.
- **HP-082**: Load and concurrency performance testing under simulated multi-tenancy.
- **HP-083**: Phased rollout strategy documentation (5% -> 25% -> 50% -> 100%).
- **HP-084**: Operational runbooks for service restart, storage rebuild, and key rotation.
- **HP-085**: Final end-to-end verification and pull-request readiness packaging.

