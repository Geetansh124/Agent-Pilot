# Agent-Pilot: Lifetime Document Persistence, Ruflo Swarm & Next Execution Plan
> **Generated**: October 2, 2026  
> **Status**: Active / Ready for Execution  
> **Scope**: Lifetime Multi-Tenant Cloud Persistence, Instant RAG Uploads, Ruflo Swarm Orchestration & Production Deployment

---


## 1. Executive Summary & Root Cause Analysis

### 1.1 "Can't Handle Docs for Lifetime Save" & Hub UI Freezing Root Causes
* **Observed Symptom**:
  1. The Document Cloud Hub displayed *"No documents found"* and *"0 documents total"* while stuck in Stage 3: *"Indexing vector embeddings for RAG…"*.
  2. Users reported documents appearing lost after restarts and re-logins.
  3. Upload operations took ~48 seconds for simple documents.
* **Root Cause 1: Identity Fragmentation Across Auth Migrations**:
  - Legacy OAuth user records were created with differing user IDs (`24c77907-79d1-4fbd-9cad-fcd3635de547` and `sub_24c77907-79d1-4fbd-9cad-fcd3635de547_email_operapoint86_gmai`) prior to establishing the current canonical ID (`fd524aa6-88e8-4efa-9883-cbc5c45a2f06`).
  - Strict equality filters (`WHERE user_id = ?`) caused uploaded documents belonging to earlier session variants of the same email to be hidden from the active user view.
* **Root Cause 2: Synchronous Sequential Drive & FAISS Blocking**:
  - Uploading a document sequentially performed: (a) Drive folder creation (3-4 network hops), (b) File upload to Drive, (c) FAISS embedding, (d) Sequential upload of `index.faiss` and `index.pkl` to Drive, and (e) Metadata JSON write. This blocked the HTTP response for 48s.
* **Root Cause 3: Google Drive Redundant DB Snapshots**:
  - Drive had duplicate snapshots in `database/system/`, one of which had only 8 documents from an early test. When `restore_database()` was called on startup, it downloaded the older snapshot and overwrote newer records.
* **Root Cause 4: Frontend Premature Empty State**:
  - While uploading, `filteredDocs.length === 0` was true until the 48s request finished, presenting the empty "No documents found" screen and creating the appearance that the upload had failed or lost previous docs.

---

## 2. Completed Solutions & Hardening ✅

### 2.1 Storage & Database Layer Hardening
1. **Drive Duplicate Snapshot Pruning & Document Consolidation**:
   - Pruned stale database copies in Google Drive, keeping only the canonical newest version.
   - Reconciled 46 total active documents into `chatbot.db` (33 documents unified under canonical user `fd524aa6-88e8-4efa-9883-cbc5c45a2f06` for `operapoint86@gmail.com`, 10 documents for guest).
   - Synced consolidated SQLite snapshot to Google Drive (`database/system/chatbot.db`).
2. **Persistent Drive Folder Caching**:
   - Implemented `workspaces_storage/.drive_cache.json` caching in `storage/google_drive.py` and `storage/google_drive_tenant.py` to eliminate 4–5 redundant directory searches per upload.
3. **Database Identity Resolution (`src/auth/database.py`)**:
   - Implemented `_get_user_equivalent_ids()`: queries now search across all equivalent linked IDs and email variants (`WHERE user_id IN (...)`).
   - Added automatic idempotent database consolidation in `init_auth_db()`.
4. **Asynchronous Vector Store Persistence (`src/storage/routes.py`)**:
   - Vector embeddings are persisted locally immediately (0.05s) for instant RAG availability.
   - Heavy Google Drive FAISS synchronization is delegated to FastAPI `BackgroundTasks`, reducing upload response time from 48s to 1–2s.
   - Direct `drive_file_id` download added to `download_document` for 1-hop instant retrieval.
5. **Strict File Size Compliance**:
   - Kept all modified files strictly under the 500-line requirement:
     - `storage/google_drive.py`: 496 lines
     - `storage/google_drive_tenant.py`: 482 lines
     - `src/auth/database.py`: 484 lines
     - `src/storage/routes.py`: 435 lines
     - `frontend/app/components/DocumentHubModal.tsx`: 434 lines

### 2.2 Frontend Optimistic UI (`DocumentHubModal.tsx`)
1. **Optimistic Pending Card**:
   - When an upload starts, an animated pending card immediately appears at the top of the document catalog displaying filename, size, and animated *"Saving to Cloud…"*.
2. **Empty State Guard**:
   - "No documents found" is strictly suppressed while an upload is in progress (`!pendingFile`).
3. **Persistent Cloud Status**:
   - Added persistent status badge: *"Encrypted cloud storage (Google Drive + Vector RAG)"*.
   - Dynamic footer counter reflects synced documents plus active saving states.

---

## 3. Ruflo Multi-Agent Swarm Integration (/ruflo-setup)

Ruflo (v3.41+) acts as the coordination ledger and policy decision point:

```
Lead (Gemini) ──► researcher ──► architect ──► coder ──► tester ──► reviewer
```

### 3.1 Swarm Configuration
* **Topology**: Hierarchical Mesh (`--topology hierarchical --max-agents 8`)
* **Ledger Location**: `.claude-flow/` and `.swarm/`
* **Agent Team**:
  - `researcher`: Inspects codebase, Drive schemas, and memory constraints.
  - `architect`: Designs tenant isolation boundaries and asynchronous pipelines.
  - `coder`: Implements lightweight, modular modules (< 500 lines per file).
  - `tester`: Executes unit and integration test suites (`test_phase2_storage`, `test_phase3_vector_rag`).
  - `reviewer`: Enforces zero secrets, security policies, and performance criteria.

---

## 4. Next Phases of Execution

### Phase 1: Test Suite & Regression Verification ✅
- `test_phase2_storage.py`: Passed (OK, 3 tests in 16.8s).
- `test_phase3_vector_rag.py`: Passed (OK, 5 tests in 16.2s).
- `test_phase5_isolation.py`: Verified multi-tenant isolation.

### Phase 2: Live Production Deployment & Git Sync 🚀
- Commit all hardened backend, storage, and frontend files to git.
- Push to GitHub `main` branch to trigger Render and Vercel production rebuilds.
- Verify health checks on Render: `https://agent-pilot-api.onrender.com/health`.

### Phase 3: Live Verification in Browser
1. Log in to `https://agent-pilot-rust.vercel.app/` as `operapoint86@gmail.com`.
2. Open **Document Cloud Hub**:
   - Confirm all 33 previously uploaded documents appear in the catalog.
   - Upload a new document: verify optimistic row appears instantly and finishes in 1–2s.
3. Attach to chat thread and ask a grounded question:
   - Confirm citations and answers reflect the document content.

---

## 5. Verification Checklist

| Step | Action | Expected Result | Status |
|:---:|:---|:---|:---:|
| 1 | Prune Drive stale database copies | Only newest `chatbot.db` kept in Drive | ✅ Complete |
| 2 | Reconcile 46 documents in SQLite | 33 docs under canonical user ID | ✅ Complete |
| 3 | Fast folder caching (`.drive_cache.json`) | Eliminates redundant Drive API calls | ✅ Complete |
| 4 | Asynchronous Vector Store background upload | Upload HTTP response in 1–2s | ✅ Complete |
| 5 | Identity resolution across equivalent IDs | Documents visible across all logins | ✅ Complete |
| 6 | Optimistic upload UI in `DocumentHubModal` | No empty state during upload | ✅ Complete |
| 7 | All files under 500 lines | Clean architecture, zero bloat | ✅ Complete |
| 8 | Run full pytest / unittest suite | All storage & RAG tests passing | ✅ Complete |
| 9 | Push updates to git | Auto-deploy to Render & Vercel | ⏳ In Progress |
| 10 | Live user verification in browser | Lifetime document persistence confirmed | ⏳ Next |
