# Agent-Pilot: Post-Upload & Next Execution Plan
> **Generated**: October 1, 2026  
> **Status**: Active / Ready for Execution  
> **Scope**: Upload Reliability, Agentic Tool Orchestration & Multi-Tenant Production Verification

---

## 1. Executive Summary & Root Cause Analysis

### 1.1 Upload Failure Root Cause
* **Observed Symptom**: `"Unable to upload document. Please ensure the backend server is active."`
* **Trigger**: A new commit (`95f93ca`) was pushed to GitHub, which initiated an automated build and container restart on Render.
* **Failure Mechanism**: During the 3–5 minute deployment window, Render/Cloudflare returned `HTTP 502 Bad Gateway` (`x-render-routing: no-deploy`). Because error gateway responses lack CORS origin headers for `https://agent-pilot-rust.vercel.app`, the browser's security model raised a generic `TypeError: Failed to fetch`.
* **Resolution Verified**:
  - Render deployment completed: `/health` returns `200 OK` with `storage.status: "connected"`.
  - Live authenticated multipart upload succeeded with `201 Created` and synced to Google Drive in 20.06s.
  - Frontend code in `frontend/app/context/AuthContext.tsx`, `frontend/app/components/DocumentHubModal.tsx`, and `frontend/app/page.tsx` was hardened with proper FormData boundary preservation and cold-start informative error messaging (commit `a1a8f19`).

---

## 2. Phased Execution Plan

```
[Phase 1: Verification & Live Proofing]
           │
           ▼
[Phase 2: Cold-Start & Keep-Alive Hardening]
           │
           ▼
[Phase 3: Agentic Execution & Specialized Subsystems]
           │
           ▼
[Phase 4: Full Multi-Tenant Security & Regression Pass]
```

---

### Phase 1: End-to-End Upload & Grounded RAG Verification
* **Goal**: Validate that users can upload documents and execute grounded RAG queries in production without friction.
* **Tasks**:
  1. **Production Sanity Check**:
     - Log in to `https://agent-pilot-rust.vercel.app/` via Google OAuth.
     - Open **Document Cloud Hub** (`Knowledge Base -> Cloud Hub`).
     - Upload a sample PDF or TXT file (e.g., `sample_upload_test.txt`).
     - Confirm modal displays document status as **Synced to Cloud**.
  2. **Thread Attachment**:
     - Click **Attach** to attach the uploaded document to the active chat thread.
     - Verify chip appears in the chat header or message input area.
  3. **Grounded Query Test**:
     - Submit prompt: *"Summarize the uploaded document and list its key points."*
     - Verify agent invokes `retrieve_documents` / RAG vector retriever.
     - Verify response contains cited snippets with factual grounding.

---

### Phase 2: Backend Cold-Start & Keep-Alive Resilience ✅
* **Goal**: Prevent Render free-tier spin-down from causing timeouts or perceived outages.
* **Tasks**:
  1. **Background Keep-Alive Cron/Ping**:
     - Implement lightweight periodic ping from the frontend or GitHub Action / Cron to `https://agent-pilot-api.onrender.com/health` every 10 minutes.
  2. **Client-Side Exponential Backoff & Retry**:
     - In `authFetch`, if a request fails with network error or 502/503 during upload or chat streaming, automatically retry once with exponential backoff before throwing.
  3. **Upload Progress Indicator**:
     - Enhance `DocumentHubModal.tsx` to display real-time upload progress stages:
       - Stage 1: Uploading payload to server...
       - Stage 2: Syncing with cloud storage...
       - Stage 3: Indexing vector embeddings for RAG...

---

### Phase 3: Autonomous Agent Execution & Tool Validation
* **Goal**: Execute and test the core agentic capabilities defined in `docs/agentic_control_system_features.md`.
* **Tasks**:
  1. **Python Sandbox Execution**:
     - Run prompt: *"Calculate compound interest on $25,000 at 8% annual return over 15 years using Python."*
     - Verify sandboxed execution in `src/tools/code_sandbox.py` produces correct math and output table.
  2. **Deep Web Research**:
     - Run prompt: *"Fetch and summarize the latest updates from https://news.ycombinator.com."*
     - Verify multi-source retrieval, URL parsing, and clean markdown summary with citations.
  3. **Multi-Agent Specialist Delegation**:
     - Test `route_to_specialist` with coder, researcher, and data-analyst roles.
     - Verify Inter-Agent Message Bus records structured artifacts.

---

### Phase 4: Production Security & Compliance Audit
* **Goal**: Confirm zero data leakage, strict multi-tenant isolation, and performance constraints.
* **Tasks**:
  1. **Cross-Tenant Boundary Test**:
     - Verify User A cannot access User B's `/api/documents` or Google Drive folders.
     - Run pytest suite: `pytest tests/test_multi_tenant_isolation.py`.
  2. **File Size & Line Count Enforcement**:
     - Ensure all modified source files remain strictly under 500 lines.
  3. **Zero Secrets in Code**:
     - Verify `.env` files and credentials remain excluded from git tracking.

---

## 3. Verification Checklist

| Step | Action | Expected Result | Status |
|:---:|:---|:---|:---:|
| 1 | Probe `/health` endpoint | HTTP 200, storage connected | ✅ Complete |
| 2 | Authenticated POST `/api/documents/upload` | HTTP 201 Created, Drive synced | ✅ Complete |
| 3 | Push FormData & error handling fix | Commit `a1a8f19` on `main` | ✅ Complete |
| 4 | User verifies upload in browser | Document appears in Cloud Hub | ⏳ Pending User Check |
| 5 | Exponential backoff retry in `authFetch` | 502/503 + network errors retried 2× | ✅ Complete |
| 6 | Upload progress stages in DocumentHubModal | 3-stage visual indicator | ✅ Complete |
| 7 | Keep-alive ping from frontend | `/health` pinged every 10 min | ✅ Complete |
| 8 | Grounded chat citation test | Accurate Q&A citing document | ⏳ Next |
| 9 | Agentic tools test (Python + Web) | Correct execution outputs | ⏳ Next |
