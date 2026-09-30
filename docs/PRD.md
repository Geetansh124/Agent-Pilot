# Product Requirements Document (PRD)
## Multi-Tenant Authentication & Persistent Google Drive Cloud Storage

| Document Metadata | Details |
|---|---|
| **Project** | Agent-Pilot |
| **Feature** | Multi-User Authentication & Persistent Cloud Document Storage |
| **Status** | Approved / In Implementation |
| **Target Version** | v2.2.0 |
| **Storage Backend** | Google Drive (Primary Cloud) + Relational DB + FAISS/RuVector |

---

## 1. Executive Summary & Vision

Agent-Pilot currently operates as a single-workspace agent where uploaded documents and conversation threads are ephemeral or tied to a single local session. 

This initiative introduces:
1. **User Authentication & Tenant Isolation**: Secure user accounts (Sign Up, Sign In, Session management) isolating threads, documents, and vector stores per user.
2. **Persistent Cloud Storage via Google Drive**: Every document uploaded by a user is automatically synchronized and stored permanently in Google Drive.
3. **Session Resiliency & On-Demand Grounding**: When a user closes the browser or restarts the app, their documents remain permanently stored in the cloud database. Upon returning, users immediately see their document catalog and can ask questions grounded in their historical files without re-uploading.

---

## 2. Target Personas

| Persona | Needs & Goals | Pain Point Addressed |
|---|---|---|
| **Research Analyst** | Uploads multiple PDFs, financial reports, and papers. Returns days later to query cross-document findings. | Previously, restarting the server or session lost access to vector indices and documents. |
| **Developer / Engineer** | Uses Python sandbox and documentation scraping while maintaining separate projects and private notes. | Needs private workspace threads separated from other team members. |
| **Enterprise User** | Demands secure authentication, reliable cloud backups on Google Drive, and zero data leakage across accounts. | Requires multi-tenant isolation and cloud persistence. |

---

## 3. Core Functional Requirements

### 3.1 Authentication & User Management
* **FR-AUTH-1 (User Registration)**: Users can create an account with email, password, and display name. Passwords must be hashed using `bcrypt` or `argon2id`.
* **FR-AUTH-2 (Secure Login & JWT)**: Users authenticate with email/password to receive a secure JWT access token (15-min expiry) and refresh token (7-day expiry).
* **FR-AUTH-3 (Session Persistence)**: When the user returns to Agent-Pilot, valid refresh tokens automatically resume their session without requiring re-login.
* **FR-AUTH-4 (User Profile & Logout)**: Header/Sidebar displays user avatar, email, and a one-click logout action that invalidates tokens.

### 3.2 Persistent Cloud Storage (Google Drive)
* **FR-STOR-1 (Google Drive Integration)**: All uploaded files (.pdf, .docx, .csv, .txt, .json) are uploaded directly to the Google Drive storage backend.
* **FR-STOR-2 (Tenant Directory Partitioning)**: Files are organized in Google Drive under tenant-specific paths:
  `Agent-Pilot/users/{user_id}/documents/{document_id}/{filename}`.
* **FR-STOR-3 (Surviving Application Restarts)**: Files remain safely in Google Drive regardless of backend restarts, container redeploys, or client closures.
* **FR-STOR-4 (Document Metadata Tracking)**: Database maintains records of Google Drive file ID, web link, file size, MIME type, chunk count, and upload timestamp.

### 3.3 Document Grounding & Persistent Vector Q&A
* **FR-RAG-1 (Automatic Ingestion & Vector Indexing)**: On upload, files are parsed, chunked, and embedded into FAISS / RuVector vector indices stored alongside the document.
* **FR-RAG-2 (Persistent Re-Attach)**: Returning users see their full document list in the Knowledge Base drawer. They can select any existing document to attach to a new or existing chat thread.
* **FR-RAG-3 (Thread-Grounded Q&A)**: LangGraph queries the user's active document embeddings, citing exact pages, sections, and chunk excerpts.

---

## 4. User Journey & Interaction Flow

```
[User Registration / Login]
         │
         ▼
[Authenticated Agent-Pilot Dashboard]
         │
         ├─────────────────────────────────────────┐
         ▼                                         ▼
[Upload New Document]                    [Open Existing Document]
         │                                         │
         ▼                                         ▼
[Stream to Google Drive Cloud Storage]    [Fetch Index from Database/Drive]
         │                                         │
         ▼                                         ▼
[Compute Vector Embeddings & Save]        [Attach to Active Chat Thread]
         │                                         │
         └─────────────────┬───────────────────────┘
                           ▼
              [Close / Reload Application]
                           │
                           ▼ (Documents & Threads Remain in Cloud)
              [User Re-Opens Agent-Pilot]
                           │
                           ▼
          [All Documents Ready for Instant Q&A]
```

---

## 5. Non-Functional Requirements

* **NFR-SEC-1 (Zero Cross-Tenant Leakage)**: Queries must enforce `WHERE user_id = :current_user` on all SQL queries and file paths.
* **NFR-SEC-2 (Encrypted Transport & Storage)**: All API communications must use TLS 1.3 / HTTPS. Service account keys stored securely via environment variables.
* **NFR-PERF-1 (Fast Cold-Start Retrieval)**: Cached vector index lookups must respond within < 250ms for attached documents.
* **NFR-REL-1 (Local Fallback)**: If Google Drive API experiences temporary rate limiting, the storage manager gracefully falls back to persistent disk with background sync retry.

---

## 6. Success Metrics & Acceptance Criteria

1. **Auth Completion**: 100% of API endpoints (except `/health` and `/api/auth/*`) reject unauthenticated requests with HTTP 401.
2. **Persistence Test**: Upload document, restart backend server, close browser, reopen: document remains visible, downloadable, and searchable.
3. **Multi-User Isolation**: User A cannot see, access, or query documents or chat threads belonging to User B.
