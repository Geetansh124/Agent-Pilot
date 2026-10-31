# End-to-end implementation prompt

**How to use:** start a fresh coding-agent session with shell, file, and browser access.
Paste everything between `===== PROMPT START =====` and `===== PROMPT END =====`. Attach
or make available the three plan documents referenced below. Expect the agent to work
phase by phase and stop only at a real blocker.

---

===== PROMPT START =====

## MISSION

Implement the DeepSeek Harness integration described in `docs/plans/` for the Agent-Pilot
repository. Work end to end: clone, branch, code, test, document, and hand back a
reviewable branch. Do not stop after a plan or a scaffold. Do not ask questions that the
documents already answer; use the decision defaults below and record any deviation.

Success means: Agent-Pilot can serve chat through `AGENT_BACKEND=harness` in staging,
with its existing auth, tenancy, RAG, storage, and SSE contract intact, and can revert to
`AGENT_BACKEND=langgraph` by changing one environment variable.

## SOURCE OF TRUTH

Read these before writing code, in this order:

1. `docs/plans/README.md` — scope and recommendation.
2. `docs/plans/deepseek-harness-integration-plan.md` — architecture, module design, data
   model, phase tasks, risks. Sections §4, §5, §6 and §8 are normative.
3. `docs/plans/adr-001-harness-integration.md` — the decision and its consequences.
4. `docs/plans/deepseek-harness-integration-tickets.md` — the ticket inventory
   (`HP-001` … `HP-085`). Implement in ticket order within each phase.
5. Agent-Pilot's own `CLAUDE.md`, `README.md`, `api_server.py`, `src/auth/database.py`,
   `src/agent/hitl.py`, `src/tools/__init__.py`, `src/mcp/mcp_server.py`,
   `langraph_rag_backend.py`, and `frontend/app/page.tsx`.

If a document and the code disagree, the code wins for current behaviour and the document
wins for intended behaviour. Record the conflict in your phase report.

## OPERATING CONTEXT

- Target repo: `https://github.com/Geetansh124/Agent-Pilot` (MIT). Clone it into
  `./agent-pilot` unless a checkout is already provided.
- Reference repo: `https://github.com/deepseek-ai/deepseek-harness` (MIT, developer
  preview). Clone read-only into `./.reference/deepseek-harness` if you need to inspect
  SDK source, protocol types, or profile patches. **Never modify the reference repo** and
  never vendor its full source into Agent-Pilot.
- Agent-Pilot stack: Python 3.10+, FastAPI (`api_server.py`), LangGraph, FAISS + BM25,
  SQLite auth/threads/messages, Next.js 14 frontend, optional Google Drive/S3 storage.
- Harness runtime: `dsh --profile sdk`, driven by `deepseek-harness-sdk` over JSON-RPC
  stdio. The published `deepseek-harness-runtime-bin` wheel embeds Node, so production
  needs **no system Node**.
- Pinned harness version for this work: resolve the newest published release at start,
  pin `deepseek-harness-sdk` and `deepseek-harness-runtime-bin` to the **same exact
  version**, and write it to `src/harness/config.py` and the Dockerfile. The checkout used
  to write these documents was `0.2.2-alpha.2`; do not blindly use that if a newer patch
  release exists. Never use a floating range for either package.

## HARD CONSTRAINTS

1. **Client contract is frozen.** `POST /api/chat` and the streaming endpoint keep their
   request and response shapes. SSE event types `token`, `tool`, `done`, `error` keep
   their existing field names. New event types are additive; existing frontend code must
   run unchanged until Phase 4 adds UI.
2. **One harness runtime per tenant.** `session.event` notifications are unfiltered
   across a runtime. Never share a `DSH_HOME`, workspace, or process between users.
3. **The harness gets no direct database or filesystem access** beyond its tenant
   workspace. All Agent-Pilot data access goes through the internal MCP server.
4. **Database changes are additive only.** `CREATE TABLE IF NOT EXISTS`; no dropped or
   rewritten columns. Rollback must not require a data migration.
5. **`AGENT_BACKEND` defaults to `langgraph`.** `harness` and `shadow` are opt-in. A
   runtime failure falls back to LangGraph and emits an audit record.
6. **Fail closed on approvals.** If the approval bridge cannot reach a decision, deny.
   Never auto-approve a sensitive tool.
7. **No secrets in config or logs.** API keys travel via child-process environment;
   never write them into `cordis.patch.yml`, SQLite, session JSONL, or logs.
8. **No public harness port and no public MCP endpoint.** Bind internal MCP to loopback
   or the private network and require a bearer token.
9. **Do not change the harness protocol.** Extending the Python transport for a Phase 6
   private notification is allowed; changing upstream semantics is not.
10. **All tests green before each phase commit.** Baseline the suite first; if it is
    already failing, record the exact failing tests and do not make them worse.

## DECISION DEFAULTS (do not block on these)

- **Hosting v1:** one API instance with a persistent disk at `$DATA_DIR`; keep the
  supervisor storage-path abstraction so a stateful worker can replace it without API
  changes. Do not attempt per-tenant POSIX homes on a scale-to-zero filesystem.
- **Provider:** NVIDIA NIM through the `llm-pi-ai` OpenAI-compatible route; fall back to
  `deepseek-official` only if Phase 0 proves the route unusable, and document it.
- **Model:** `nvidia/nemotron-3-ultra-550b-a55b`, matching Agent-Pilot today.
- **Streaming:** Phase 2 replays the chunk stream embedded in `assistant/message`; Phase 6
  adds live deltas via a plugin. If Phase 6 is blocked, keep Phase 2 and mark the gap.
- **Approvals:** bridge to the existing `HITLManager`; one-shot decisions only.
- **Sessions:** `session_id = "ap-" + thread_id`; one working directory per thread at
  `<tenant_home>/workspace/<thread_id>`.
- **Tests:** Python `unittest`, discovered with
  `python -m unittest discover -s tests -p "test_*.py"`. Frontend: existing build plus
  Playwright if present.
- **Commits:** small, per ticket; reference the ticket id. Follow the repository's
  `CLAUDE.md` attribution rules.

## PRE-FLIGHT (do this before Phase 0)

1. Clone Agent-Pilot. Record `git rev-parse HEAD` as the baseline commit.
2. Create `.venv`, install `requirements.api.txt` (plus dev/test extras you need), and
   run the full suite. Save the baseline output to `artifacts/baseline-tests.txt`.
3. Create branch `lemon/harness-integration` (or `feat/harness-integration` if the repo
   has a naming convention) and an empty checkpoint commit.
4. Create `artifacts/` and add it to `.gitignore`; it holds logs, fixtures, and evidence,
   not product code.
5. Write `docs/plans/implementation-log.md` with the baseline commit, version pins, and
   a table you update at every phase gate.

## EXECUTION PROTOCOL

For every ticket:

1. Read the ticket and the plan section it references.
2. Read every file you will touch before editing it.
3. Write or update a failing test where the behaviour is testable.
4. Implement the smallest change that satisfies acceptance.
5. Run the focused test, then the full suite.
6. Commit with a message like `HP-021: add HarnessBackend stream and invoke`.
7. Append evidence to `docs/plans/implementation-log.md`: what changed, test command and
   result, and any deviation.

For every phase:

1. Confirm all its tickets meet acceptance.
2. Run the phase gate commands.
3. Produce the phase report (template below) and stop only if a stop condition applies.
4. Move on without asking for permission.

## PHASE PLAN

### Phase 0 — Feasibility gate (HP-001 … HP-006)

Goal: prove the runtime, provider route, event schema, and sandbox on the deployment base
image before product code.

Build:

1. A reproducible environment: `python:3.11-slim` plus pinned SDK and runtime wheels.
   Verify `dsh --version` works with **no** system Node and no `~/.dsh` present.
2. `scripts/spike_minimal.py`: launches `DeepSeekHarness` with an isolated `DSH_HOME`,
   `profile="sdk"`, `provider="nvidia"`, the pinned model, the NVIDIA patch, and
   `env={"NVIDIA_API_KEY": ...}`; runs one text turn and one tool-using turn.
3. `harness/profiles/nvidia.patch.yml`: a hand-declared `llm-pi-ai` route with
   `api: openai-completions`, `baseURL: https://integrate.api.nvidia.com/v1`,
   `apiKeyEnv: NVIDIA_API_KEY`, and an explicit model entry. Follow plan §4.7.
4. `tests/fixtures/harness/`: captured `session.event` and `session.status` sequences
   for text, tool call/result, tool error, compaction, approval request, and user
   question. Redact any secrets and absolute home paths.
5. `tests/fixtures/harness/sandbox.md`: evidence that `workspace-write` denies a write
   outside the tenant root.
6. `docs/plans/spike-report.md`: cold-start seconds, RSS, idle CPU, streaming behaviour,
   and a go/no-go.

Gate:

```bash
python scripts/spike_minimal.py
python -m unittest discover -s tests -p "test_*.py"
grep -R "api_key\|nvapi-" tests/fixtures/harness || true
```

Do not proceed to Phase 1 if the tool-using turn fails or the sandbox is not confined.
If NVIDIA is unusable, switch the default provider to `deepseek-official`, record why,
and continue.

### Phase 1 — Supervisor and tenancy (HP-010 … HP-015)

Build `src/harness/config.py`, `errors.py`, `runtime.py`, `sessions.py`, and the
`harness_sessions` migration/helpers.

Required behaviour:

- Salted tenant path: `HMAC-SHA256(HARNESS_PATH_SALT, user_id)`, hex, under
  `$HARNESS_HOME_ROOT/<hash>/home`.
- Lazy launch, `initialize` probe, LRU cap, idle eviction, restart with bounded backoff,
  graceful `close()` and child reaping.
- Per-`(tenant, session)` lock; requests for different sessions may overlap.
- Explicit `DSH_HOME` on every launch; never allow fallback to `~/.dsh`.
- Typed errors: `RuntimeUnavailable`, `SessionBusy`, `ProtocolError`, `QuotaExceeded`.

Gate:

```bash
python -m unittest discover -s tests -p "test_harness_*.py"
python -m unittest discover -s tests -p "test_*.py"
```

Evidence must show two tenants with distinct homes, a denied cross-tenant resume, and no
surviving `dsh` child after eviction.

### Phase 2 — Chat backend and SSE (HP-020 … HP-025)

Build `translate.py`, `backend.py`, `router.py`, `wire.py`; wire `api_server.py` without
changing signatures.

Required behaviour:

- Pre-flight order preserved exactly: ownership → rate limit → prompt validation → cost
  budget → backend call.
- Run `Session.run()` in a worker thread and translate `on_notification` callbacks for
  live events; emit `done` exactly once when `run()` returns. Do **not** reimplement the
  SDK's completion rules: ordinary prompts end on `session.status=idle` after admission,
  command queries on `session.query.completed`.
- `assistant/message.data.stream` chunks are replayed as ordered `token` events at commit;
  do not invent synthetic chunking when the stream is present.
- One `{"type":"tool","name":...}` per `tool/call`, matching the current UI's badge
  behaviour. `tool/result` may emit the new optional `tool_result` event.
- Errors are sanitised: no stack traces, absolute paths, provider payloads, or secrets.
- LangGraph path remains byte-compatible with today.

Gate:

```bash
python -m unittest discover -s tests -p "test_harness_*.py"
python -m unittest discover -s tests -p "test_*.py"
curl -N -s -X POST localhost:8000/api/chat/stream -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"message":"hello","thread_id":"'$THREAD'"}'
```

Record the SSE transcript for a text turn, a tool turn, and a runtime-failure fallback.

### Phase 3 — MCP bridge and RAG parity (HP-030 … HP-034)

Extend `src/mcp/mcp_server.py` with a Streamable HTTP transport at `POST /mcp`
(`GET /mcp` for SSE if needed), internal bearer auth from `MCP_INTERNAL_TOKEN`,
constant-time comparison, and JSON-RPC error mapping.

**Current state to fix first:** `POST /mcp` in `api_server.py` is unauthenticated and
non-streaming — it forwards the JSON body to `mcp_server.handle_request`. Until auth and
tenant resolution land, do not register any mutating tool and do not expose the endpoint
beyond loopback/private networking. Treat the existing public route as a security bug.

Required behaviour:

- Read-only tools first: `rag_tool`, `web_search`, `scrape_web`, `read_workspace_file`,
  `query_database`, `retrieve_memory`, `get_current_datetime`.
- Mutating tools only when the tenant approval policy allows them, and only through
  `HITLManager`.
- Tenant identity is resolved server-side from the token/headers; model-supplied
  `thread_id` or `user_id` arguments are ignored for tenant-scoped tools.
- `rag_tool` returns context, citations, metadata, scores, and source files, and reports
  whether the thread has a document so the model can ask for an upload.
- Ship `harness/profiles/ap-tools.patch.yml` with the `mcp-ap` client config.

Gate:

```bash
python -m unittest discover -s tests -p "test_*mcp*.py"
python -m unittest discover -s tests -p "test_*.py"
```

Evidence: a document question answered with AP citations, and a rejected cross-tenant
tool call.

### Phase 4 — Approvals and questions (HP-040 … HP-044)

Build `src/harness/approvals.py` and the endpoints below, plus the frontend modal.

```text
POST /api/threads/{thread_id}/approvals/{request_id}
     {"decision": "allowed-once" | "rejected" | "cancelled"}
GET  /api/threads/{thread_id}/approvals
POST /api/threads/{thread_id}/questions/{request_id}
     {"answers":[{"id":"...","selected":["..."],"custom":"..."}]} or {"cancelled":true}
```

Required behaviour:

- Decisions are one-shot; duplicate or late decisions return 409.
- Ownership is enforced on every endpoint; unauthenticated or cross-user requests 404.
- Missing bridge, expiry, or transport loss denies the tool and records an audit event.
- Existing `HITLManager` API used by LangGraph keeps working; extend, do not replace.

Gate: tests for approve-once, reject, cancel, duplicate, wrong user, bridge down, and
expired request; a Playwright (or manual, recorded) UI approval flow.

### Phase 5 — Persistence, sync, lifecycle (HP-050 … HP-055)

Implement `harness_events`, `harness_approvals`, and the `messages` projection exactly as
plan §5.1–5.4. Sync JSONL plus a manifest (session id, format version, sha256, size) using
the existing storage abstraction. Restore before `resume_session`; verify checksum.

Required behaviour:

- `UNIQUE(thread_id, seq)` makes appends idempotent.
- Projection happens in one SQLite transaction after the event exists durably.
- Thread delete removes session JSONL and rows; rename is AP-only.
- A reconciliation script replays gaps from `last_event_seq` and supports `--dry-run`.

Gate: kill the runtime mid-turn, restart, resume, and show no duplicated or missing
messages; restore a session from remote storage in a clean tenant home.

### Phase 6 — Live streaming and shadow eval (HP-060 … HP-064)

Write `harness/plugins/stream-forwarder` (TypeScript, built with Node 24 + pnpm only at
build time) to forward in-process `AssistantStreamFrame`s as `ap/stream` notifications.
Extend `src/harness/wire.py` to consume them without breaking stock `HarnessClient`.
Fall back to Phase 2 replay when the plugin is absent.

Gate:

- Token-order test across text, tool, and interleaved turns.
- Shadow run of 40 prompts comparing LangGraph and harness: tool selection, latency,
  token counts, and answer quality. Store only aggregate diffs.
- Promotion criteria: ≥95% parity, no P0 safety regression, p95 within +25%.

If the plugin cannot be built reproducibly, keep replay, mark HP-060/061/062 blocked with
evidence, and continue to Phase 7.

### Phase 7 — Observability, cost, quotas (HP-070 … HP-074)

Emit structured audit records for turn start/end, tool calls, approvals, restarts, and
fallbacks. Add per-tenant/model/backend token and cost accounting. Add an admin-only
metrics endpoint (or the host's equivalent). Enforce `HARNESS_MAX_RUNTIMES`,
`HARNESS_MAX_CONCURRENT_TURNS`, `HARNESS_TURN_TIMEOUT_S`, `HARNESS_MAX_TOOL_CALLS`, with
429 + `Retry-After`.

Gate: a metrics snapshot showing counts and cost for two tenants; quota test returns 429
and writes an audit entry.

### Phase 8 — Hardening and rollout (HP-080 … HP-085)

Run the chaos matrix: kill -9 the runtime, truncate a JSONL tail, block MCP, delay
approvals, exhaust the runtime pool, fill the disk. Every case degrades to a typed error
or LangGraph. Run the security checklist in plan §4.10, a 50-VU load test, and document
rollout stages 5% → 25% → 50% with automatic rollback triggers. Write runbooks for
restart, rebuild, restore, and key rotation.

Gate: chaos tests green, p95 documented, rollback rehearsed, runbooks reviewed.

## FILE MAP

Create (do not rename existing modules):

```text
src/harness/__init__.py
src/harness/config.py        HarnessSettings, version pins, path policy
src/harness/errors.py        typed failures → HTTP mapping
src/harness/runtime.py       RuntimeSupervisor, TenantRuntime
src/harness/sessions.py      SessionMapper, restore/reconcile
src/harness/translate.py     session.event → AP SSE
src/harness/approvals.py     ApprovalBridge
src/harness/backend.py       HarnessBackend (ChatBackend protocol)
src/harness/router.py        backend selection + fallback
src/harness/store.py         event append + message projection
src/harness/sync.py          JSONL/manifest sync and restore
src/harness/metrics.py       audit, cost, counters
src/harness/wire.py          thin SDK transport wrapper
harness/profiles/*.yml       pinned profile patches
harness/plugins/stream-forwarder/  Phase 6 plugin
scripts/spike_minimal.py
scripts/harness_reconcile.py
tests/fixtures/harness/
tests/test_harness_*.py
tests/integration/test_harness_*.py
frontend/app/components/ApprovalModal.tsx
docs/plans/spike-report.md
docs/plans/implementation-log.md
```

Modify minimally: `api_server.py`, `src/auth/database.py`, `src/mcp/mcp_server.py`,
`src/agent/hitl.py`, `frontend/app/page.tsx`, `requirements.api.txt`, `Dockerfile.api`,
`.env.example`, `render.yaml` (or the active deployment manifest).

## REPOSITORY HYGIENE

- Do not commit `.env`, `artifacts/`, `.venv/`, `node_modules/`, harness homes, session
  JSONL, or any key material.
- Keep new modules under ~400 lines; split by responsibility rather than growing
  `api_server.py`.
- Keep imports at the top; no wildcard imports; type-hint public functions.
- Add a short docstring only where behaviour is non-obvious.
- Update `requirements.api.txt` with exact pins for the two harness wheels.
- Do not reformat unrelated files or rename existing symbols.

## PHASE REPORT TEMPLATE

After each phase, append this to `docs/plans/implementation-log.md` and print it:

```text
PHASE <n> — <name>
Status: complete | partial | blocked
Tickets: HP-xxx … HP-xxx
Changed: <files>
Tests: <command> → <passed/failed counts>; new tests: <names>
Evidence: <artifact paths, transcripts, metrics>
Deviations: <none | what and why>
Risks / follow-ups: <items>
Next: <phase n+1 or stop reason>
```

## STOP CONDITIONS

Stop and report instead of guessing when:

- The published SDK/runtime wheels cannot be installed on the target platform.
- The NVIDIA route fails tool calling after two documented attempts (use fallback, note it).
- The baseline test suite has failures that make a phase gate unmeasurable.
- A required change would break the SSE/auth contract or require a destructive migration.
- You cannot isolate tenants (shared home/process) with the pinned runtime.
- A secret would have to be committed or exposed to make progress.

Do not stop for missing optional UI polish, a slow test, or an open product question that
has a default above.

## DEFINITION OF DONE

- `AGENT_BACKEND=harness` serves chat in staging for a test tenant; `langgraph` still works.
- Existing SSE clients, auth, thread CRUD, RAG citations, and storage sync pass regression.
- Two-tenant isolation, sandbox confinement, approval fail-closed, and chaos tests pass.
- Resume after a crash produces no duplicate or missing messages.
- Harness versions are pinned; upgrade and rollback are documented and rehearsed.
- `docs/plans/implementation-log.md` has a green gate entry for every phase.
- Branch is pushed and a pull request is opened with a summary, test evidence, rollout
  plan, and rollback instructions. Do not merge it.

## START

Begin with pre-flight and Phase 0. Do not produce another plan. Do not ask for approval
between phases. Report only at phase gates or stop conditions.

===== PROMPT END =====
