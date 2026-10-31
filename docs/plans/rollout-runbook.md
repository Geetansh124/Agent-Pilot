# DeepSeek Harness Rollout & Operational Runbook

## 1. Overview
This runbook defines the phased deployment strategy, automated rollback triggers, and operational maintenance procedures for the DeepSeek Harness (`dsh`) backend integration within Agent-Pilot.

---

## 2. Phased Rollout Schedule (HP-083)

| Stage | Target Population | Routing Configuration | Success Criteria | Duration |
| :--- | :--- | :--- | :--- | :--- |
| **Stage 1 (Canary)** | 5% (Internal devs) | `AGENT_BACKEND=shadow` | Tool parity >=95%, 0 security violations, p95 overhead <=25% | 48 hours |
| **Stage 2 (Staging)** | 25% (Beta team opt-in) | `AGENT_BACKEND=harness` (targeted) | 0 critical crash loops, quota controls functioning (429 verified) | 72 hours |
| **Stage 3 (Gradual Prod)** | 50% (Production users) | `AGENT_BACKEND=harness` (balanced) | p95 latency within baseline, zero data corruption incidents | 96 hours |
| **Stage 4 (Full GA)** | 100% (All traffic) | `AGENT_BACKEND=harness` | Standard operating posture | Permanent |

---

## 3. Rollback Protocol & Automatic Triggers

### 3.1 Immediate Rollback Triggers
Automatic or operational reversion to LangGraph MUST occur immediately if any of the following occur:
1. **Safety Regression**: Any detected path traversal attempt escaping `<tenant_home>/workspace` or unredacted credentials in SSE streams.
2. **Tool Selection Parity Drop**: Aggregate tool parity falls below 95%.
3. **Latency Degradation**: p95 response latency exceeds +25% above LangGraph baseline.
4. **Unhandled Runtime Crashes**: Process panic or unhandled exception rate > 1.0%.

### 3.2 Instant Rollback Procedure (Zero Downtime)
1. Update environment variable in container deployment or `.env`:
   ```bash
   AGENT_BACKEND=langgraph
   ```
2. Trigger rolling restart of `api_server`:
   ```bash
   # Docker / Container restart
   docker restart agent-pilot-api
   ```
3. Verify backend active status:
   - LangGraph checkpoints remain untouched and active.
   - All previous chat history in SQLite `messages` table remains fully intact.
   - No database schema migrations or rollbacks required due to non-destructive additive DDL.

---

## 4. Operational Maintenance Runbooks (HP-084)

### 4.1 Service Restart & Health Verification
1. Start API Server:
   ```bash
   python api_server.py
   ```
2. Verify Admin Metrics Endpoint:
   ```bash
   curl -H "Authorization: Bearer <ADMIN_JWT_TOKEN>" http://localhost:8000/api/admin/metrics/harness
   ```
   Expect HTTP 200 with JSON payload containing `total_turns`, `tenants`, and `total_cost_usd`.

### 4.2 Storage Rebuild & Offline Reconciliation
If a node crashes mid-turn or unprojected events exist in `harness_events`:
1. Execute reconciliation in dry-run mode:
   ```bash
   python scripts/harness_reconcile.py --db chatbot.db --dry-run
   ```
2. Execute actual repair and projection replay:
   ```bash
   python scripts/harness_reconcile.py --db chatbot.db
   ```
   Inspect summary output to ensure all gaps and unprojected messages are synced to SQLite `messages`.

### 4.3 Session Restore from Remote Storage
If local workspace or tenant home disk is lost:
1. Ensure remote storage has synced `events.jsonl` and `manifest.json`.
2. Run restore with SHA-256 verification via `SessionSyncManager`:
   ```python
   from src.harness.config import get_harness_settings
   from src.harness.sync import SessionSyncManager

   settings = get_harness_settings()
   sync_mgr = SessionSyncManager(settings)
   success, msg = sync_mgr.restore_session(user_id="<USER_ID>", thread_id="<THREAD_ID>")
   assert success, f"Restore failed: {msg}"
   ```

### 4.4 Token & Salt Key Rotation
1. **MCP Internal Bearer Token Rotation**:
   - Update `MCP_INTERNAL_TOKEN=<NEW_SECURE_TOKEN>` in environment.
   - Rolling restart of services. Handshake methods continue while internal tool calls switch instantly.
2. **Tenant Path Salt Rotation (`HARNESS_PATH_SALT`)**:
   - If path salt is rotated, existing tenant home directories will hash to new deterministic paths.
   - Run migration script to move existing `<home_root>/<old_hash>` directories to `<home_root>/<new_hash>`.

