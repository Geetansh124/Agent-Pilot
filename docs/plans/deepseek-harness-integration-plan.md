# DeepSeek Harness Integration Plan

## §1. Architecture Overview

Agent-Pilot integrates DeepSeek Harness as a pluggable backend implementing the `ChatBackend` protocol. The core API server (`api_server.py`) inspects `AGENT_BACKEND` to route requests to either `LangGraphBackend` or `HarnessBackend`.

```
[ Client / Web UI ]
       │
       ▼ (POST /api/chat or /api/chat/stream)
[ FastAPI Server (api_server.py) ]
       │
       ├── Pre-flight: Auth (JWT) ➔ Rate Limit ➔ Prompt Guard ➔ Cost Budget
       │
  [ Backend Router (src/harness/router.py) ]
       ├── AGENT_BACKEND="langgraph" ──> [ LangGraph Backend ]
       └── AGENT_BACKEND="harness"   ──> [ Harness Backend (src/harness/backend.py) ]
                                              │
                                 [ Runtime Supervisor (src/harness/runtime.py) ]
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
         [ Tenant A Process (dsh) ]                      [ Tenant B Process (dsh) ]
         DSH_HOME: /dsh/tenants/<h1-salt>/home           DSH_HOME: /dsh/tenants/<h2-salt>/home
         Workspace: .../workspace/<thread_id>           Workspace: .../workspace/<thread_id>
                      │                                               │
                      └─────────────── JSON-RPC Loopback ─────────────┘
                                              ▼
                                 [ Internal MCP Server (/mcp) ]
                                 Bearer Auth: MCP_INTERNAL_TOKEN
                                              │
                       ┌──────────────────────┼──────────────────────┐
                       ▼                      ▼                      ▼
                  [ RAG Tool ]          [ Web Search ]         [ SQLite / File Tools ]
```

---

## §4. Runtime Architecture & Tenancy (Normative)

### §4.1 Tenancy & Isolation
- **No Shared State**: Every tenant (`user_id`) receives an isolated `DSH_HOME` directory.
- **Salted Path Policy**:
  ```python
  tenant_dir_name = hmac.new(
      HARNESS_PATH_SALT.encode("utf-8"),
      user_id.encode("utf-8"),
      hashlib.sha256
  ).hexdigest()
  tenant_home = os.path.join(HARNESS_HOME_ROOT, tenant_dir_name, "home")
  ```
- **Workspace Confinement**: Thread working directories are isolated under `<tenant_home>/workspace/<thread_id>`. File writes outside this tree are denied by sandbox policy.

### §4.2 Supervisor Lifecycle
- Managed by `RuntimeSupervisor` (`src/harness/runtime.py`).
- **Lazy Initialization**: Process spawns on demand when a tenant turn begins.
- **LRU Pool & Eviction**: Enforce `HARNESS_MAX_RUNTIMES` (default: 10). Least recently used idle runtimes are gracefully closed (`SIGTERM` -> timeout -> `SIGKILL`).
- **Idle Timeout**: Runtimes idle for `HARNESS_IDLE_TIMEOUT_S` (default: 300s) are evicted.
- **Concurrency**: Per-`(tenant, session)` asyncio / threading lock. Cross-session turns for different threads execute concurrently.

### §4.3 Error Handling & Fail-Safe Fallback
- Typed exceptions in `src/harness/errors.py`:
  - `RuntimeUnavailable`
  - `SessionBusy`
  - `ProtocolError`
  - `QuotaExceeded`
- If `HarnessBackend` fails during launch or initialization, it automatically falls back to `LangGraphBackend` when configured, recording an audit event.

---

## §5. Data Model & Persistence (Normative)

All database schema additions are strictly additive in SQLite (`chatbot.db`).

### §5.1 `harness_sessions` Table
```sql
CREATE TABLE IF NOT EXISTS harness_sessions (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    harness_session_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    last_event_seq INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(thread_id)
);
```

### §5.2 `harness_events` Table
```sql
CREATE TABLE IF NOT EXISTS harness_events (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(thread_id, seq)
);
```

### §5.3 `harness_approvals` Table
```sql
CREATE TABLE IF NOT EXISTS harness_approvals (
    id TEXT PRIMARY KEY,
    request_id TEXT UNIQUE NOT NULL,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    arguments JSON NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('pending', 'allowed-once', 'rejected', 'cancelled')),
    decided_by TEXT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP
);
```

### §5.4 Projection to `messages`
When `assistant/message` commits:
1. An event is recorded into `harness_events`.
2. A single atomic SQLite transaction projects the message content into `messages` (`role='assistant'`) with `tool_calls` JSON, maintaining exact compatibility with existing thread UI views.

---

## §6. MCP Bridge & Tool Protocol (Normative)

### §6.1 Security & Transport
- Exposed at `POST /mcp` in `api_server.py`.
- **Authentication**: Requires `Authorization: Bearer <MCP_INTERNAL_TOKEN>`.
- Constant-time token verification via `hmac.compare_digest`.
- Bind to loopback/private network only.

### §6.2 Tool Categories
- **Read-Only Tools** (allowed automatically):
  - `rag_tool`: Vector & BM25 hybrid context search with citation scores.
  - `web_search`: DuckDuckGo / web search.
  - `scrape_web`: Text extraction from URLs.
  - `read_workspace_file`: Scoped to tenant workspace.
  - `query_database`: Read-only queries.
  - `retrieve_memory`: Agent long-term memory lookup.
- **Sensitive / Mutating Tools** (gated by `HITLManager`):
  - `write_workspace_file`, `delete_workspace_file`, `call_api`, `run_code_task`.
  - Sensitive tools trigger `ApprovalBridge` and yield an approval request before continuing.

---

## §8. Hardening, Observability & Rollback (Normative)

### §8.1 Observability & Audit
- Structured audit logs via `src/observability/audit_logger.py` with event types:
  - `harness_turn_start`, `harness_turn_end`, `harness_tool_call`, `harness_approval`, `harness_fallback`.
- Token accounting and cost calculation via `src/harness/metrics.py`.

### §8.2 Rollback Runbook
- Immediate rollback: set `AGENT_BACKEND=langgraph` and restart container.
- No database downgrades required due to non-destructive additive DDL.
- In-flight LangGraph checkpoints remain untouched.
