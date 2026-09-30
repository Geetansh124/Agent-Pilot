# Implementation Tasks & Roadmap
## Multi-Tenant Authentication & Persistent Google Drive Cloud Storage

| Sprint Roadmap | Details |
|---|---|
| **Phase 1** | Backend Authentication & Multi-Tenant Database |
| **Phase 2** | Google Drive Storage Adapter & Tenant Folder Scoping |
| **Phase 3** | Multi-Tenant Vector Store & Grounded RAG Ingestion |
| **Phase 4** | Frontend Auth Dialog, Session Context & Document Hub |
| **Phase 5** | End-to-End Integration, Security Scan & Verification |

---

## Phase 1: Backend Authentication & Data Models

### Task 1.1 — Database Migration & User Schemas
* **Assignee**: `system-architect`
* **Objective**: Create `users`, `refresh_tokens`, and add `user_id` foreign keys to `threads`, `documents`, and `messages` in `chatbot.db`.
* **Acceptance Criteria**:
  - [x] Migration runs idempotently on startup.
  - [x] Foreign keys cascade on user deletion.
  - [x] Indices created on `(user_id, created_at)`.

### Task 1.2 — Authentication Service & Password Hashing
* **Assignee**: `coder`
* **Objective**: Implement password hashing (`passlib[bcrypt]`), JWT encoding/decoding, and token generation utilities in backend.
* **Acceptance Criteria**:
  - [x] Secure token expiry (15m access, 7d refresh).
  - [x] `get_current_user` FastAPI dependency extracts and verifies JWT.

### Task 1.3 — Auth REST API Endpoints
* **Assignee**: `coder`
* **Objective**: Expose `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, and `/api/auth/me`.
* **Acceptance Criteria**:
  - [x] Duplicate email registration returns HTTP 409.
  - [x] Invalid credentials return HTTP 401.
  - [x] Protected endpoints reject missing/invalid tokens.

---

## Phase 2: Google Drive Multi-Tenant Storage Adapter

### Task 2.1 — Multi-Tenant Google Drive Folder Isolation
* **Assignee**: `system-architect` & `coder`
* **Objective**: Extend Google Drive storage service to organize files under `Agent-Pilot/users/{user_id}/documents/{doc_id}/`.
* **Acceptance Criteria**:
  - [x] Creates user directory on first upload.
  - [x] Upload returns `drive_file_id`, `web_view_link`, and file size.
  - [x] Storage metadata saved in `documents` database table.

### Task 2.2 — Background Document Recovery & Persistence
* **Assignee**: `coder`
* **Objective**: Implement `/api/documents` endpoint listing all documents belonging to `current_user`.
* **Acceptance Criteria**:
  - [x] When user reloads the app, existing uploaded documents are listed immediately.
  - [x] Files remain persistent in Google Drive after container restarts.

---

## Phase 3: Multi-Tenant Vector RAG Pipeline

### Task 3.1 — Scoped FAISS / RuVector Storage
* **Assignee**: `coder`
* **Objective**: Save vector embeddings in user-scoped partitions (`storage/users/{user_id}/vectors/{doc_id}/`).
* **Acceptance Criteria**:
  - [x] Vector store file syncs to Google Drive upon generation.
  - [x] Cache warms up on demand when attaching a historical document.

### Task 3.2 — Document Attach & Grounded Q&A
* **Assignee**: `coder`
* **Objective**: Allow users to attach any historical document from their Google Drive catalog to an active thread.
* **Acceptance Criteria**:
  - [x] Grounded Q&A cites sections from the user's selected document.
  - [x] Cross-tenant access is blocked with HTTP 404/403.

---

## Phase 4: Next.js Frontend Integration

### Task 4.1 — Auth Context & State Management
* **Assignee**: `coder`
* **Objective**: Create `AuthContext` in Next.js managing user state, tokens in memory/cookie, and automatic refresh.
* **Acceptance Criteria**:
  - [ ] State reflects authenticated vs guest.
  - [ ] Requests automatically attach `Authorization: Bearer <token>`.

### Task 4.2 — Auth Modal Component (Sign In / Register)
* **Assignee**: `coder`
* **Objective**: Build glassmorphic login modal following `docs/design.md`.
* **Acceptance Criteria**:
  - [ ] Smooth switching between Sign In and Create Account tabs.
  - [ ] Field validation for email format and password length.

### Task 4.3 — Knowledge Base Document Hub Modal
* **Assignee**: `coder`
* **Objective**: Build Document Cloud Hub modal displaying user's persistent Google Drive documents with "Attach to Chat" action.
* **Acceptance Criteria**:
  - [ ] Shows file list with Google Drive synced status badge.
  - [ ] Clicking "Attach" links the document to the current conversation.

---

## Phase 5: Testing, Validation & Security Audit

### Task 5.1 — Multi-Tenant Isolation Tests
* **Assignee**: `tester`
* **Objective**: Automated test asserting that User A cannot retrieve or query User B's documents or threads.
* **Acceptance Criteria**:
  - [ ] Test suite executes in CI/pytest.
  - [ ] All cross-tenant requests fail safely.

### Task 5.2 — Security Envelope Audit & Swarm Review
* **Assignee**: `reviewer`
* **Objective**: Comprehensive code review for OWASP compliance, zero secrets, and file size constraints (< 500 lines).
* **Acceptance Criteria**:
  - [ ] Security audit passes with zero critical findings.
  - [ ] All code files remain strictly under 500 lines.
