# Ruflo Coordination & Architectural Memory (ADR Ledger)
## Agent-Pilot Project Knowledge Base

| Ledger Metadata | Details |
|---|---|
| **Framework** | RuFlo v3.0+ Meta-Harness |
| **Swarm Topology** | Hierarchical Mesh (Lead ↔ Architect ↔ Coder ↔ Tester ↔ Reviewer) |
| **Memory Backend** | Hybrid Vector + Relational Memory (`.claude-flow/data`) |

---

## 1. Architectural Decision Records (ADRs)

### ADR-001: Multi-Tenant Data Isolation Strategy
* **Date**: 2026-09-30
* **Status**: Accepted
* **Context**: Different users need to upload and manage documents independently without data leakage.
* **Decision**: Adopt row-level tenant scoping via `user_id` on all operational tables (`users`, `documents`, `threads`, `messages`).
* **Consequences**: Every endpoint must be guarded by `get_current_user`. All queries must filter by `user_id`.

---

### ADR-002: Google Drive as Primary Cloud Document Storage
* **Date**: 2026-09-30
* **Status**: Accepted
* **Context**: When users close the app or the backend server redeploys on cloud hosts (e.g. Render / Cloud Run), local files are lost.
* **Decision**: Use Google Drive API via a dedicated Service Account connected to a **Google Workspace Shared Drive**. Files are stored permanently under `users/{user_id}/documents/{doc_id}/`.
* **Critical Gotcha**: Standalone Service Accounts have **0 MB personal storage quota**. A **Shared Drive** must be used so storage quotas attach to the organization.
* **Consequences**: Uploads are resilient and survive restarts. Document Q&A can resume immediately upon logging in.

---

### ADR-003: JWT Authentication with Rotating Refresh Tokens
* **Date**: 2026-09-30
* **Status**: Accepted
* **Context**: Stateless API authentication that supports both browser web sessions and potential CLI/SDK integrations.
* **Decision**: Issue a short-lived access token (15 minutes) and a long-lived refresh token (7 days) stored hashed in the database.
* **Consequences**: Minimizes token interception risk while providing seamless session resumption when users reopen the application.

---

### ADR-004: Persistent Multi-User Vector Indexing
* **Date**: 2026-09-30
* **Status**: Accepted
* **Context**: Vector embeddings are expensive to recalculate every time a user starts a conversation.
* **Decision**: Serialize vector indices (`index.faiss` / `index.pkl`) and synchronize them directly to Google Drive under `users/{user_id}/vectors/{doc_id}/`. On cold start, the backend downloads the cached index once.
* **Consequences**: Sub-second cold-start grounding when attaching documents to chat threads.

---

### ADR-005: Next.js App Router Static Asset Conventions
* **Date**: 2026-09-30
* **Status**: Accepted
* **Context**: Next.js App Router reserves `/icon.jpg` and `/icon.svg` inside `app/` as special metadata icons, causing 500 errors when rendered as `<img src="/icon.jpg" />`.
* **Decision**: Store all application branding images in `public/logo.jpg` and `public/logo.svg` to avoid Next.js metadata route collisions.

---

## 2. Key Environment & Credential Registry

| Configuration Key | Required | Purpose |
|---|---|---|
| `JWT_SECRET_KEY` | Yes | Signs and verifies user authentication tokens |
| `STORAGE_BACKEND` | Yes | Set to `google_drive` for cloud persistence |
| `GOOGLE_DRIVE_FOLDER_ID` | Yes | Target Shared Drive folder ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Yes | Google Service Account credentials JSON string |
| `DATABASE_URL` | Optional | SQLite default (`sqlite:///chatbot.db`), PostgreSQL optional |

---

## 3. Swarm Routing Topology

```
             ┌─────────────────────────┐
             │       Swarm Lead        │
             └────────────┬────────────┘
                          │
         ┌────────────────┴────────────────┐
         ▼                                 ▼
┌──────────────────┐             ┌──────────────────┐
│ system-architect │             │ security-reviewer│
│ (Schema & Design)│             │ (OWASP & Tenant) │
└────────┬─────────┘             └──────────────────┘
         │
         ▼
┌──────────────────┐
│      coder       │
│(API, Drive & UI) │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│      tester      │
│(Isolation Tests) │
└──────────────────┘
```
