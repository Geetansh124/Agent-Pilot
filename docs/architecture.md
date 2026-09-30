# System Architecture & Technical Specification
## Multi-Tenant Authentication & Persistent Google Drive Cloud Storage

| Architecture Spec | Details |
|---|---|
| **System** | Agent-Pilot Autonomous Workspace |
| **Backend** | FastAPI (Python 3.10+) + LangGraph + FAISS/RuVector |
| **Frontend** | Next.js 14 (App Router) + Tailwind CSS + Lucide Icons |
| **Storage Layer** | Google Drive API (Service Account / Shared Drive) + SQLite/PostgreSQL |
| **Auth Protocol** | JWT (RS256/HS256) with Access (15m) & Refresh (7d) Tokens |

---

## 1. High-Level System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Next.js 14 Frontend Client                            │
│  ┌────────────────────┐ ┌──────────────────────┐ ┌───────────────────┐ │
│  │ Auth Context / UI  │ │ Chat & Tool Pipeline │ │ Document Library  │ │
│  │ (Login/Register)   │ │ (Stream & Feedback)  │ │ (Drive Sync View) │ │
│  └─────────┬──────────┘ └──────────┬───────────┘ └─────────┬─────────┘ │
└────────────┼───────────────────────┼───────────────────────┼───────────┘
             │ Bearer JWT            │ SSE Stream / REST     │ Multi-part
             ▼                       ▼                       ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend Orchestrator                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Auth & Tenant Middleware (Validates JWT, extracts user_id)        │  │
│  └─────────────────────────────────┬────────────────────────────────┘  │
│                                    ▼                                   │
│  ┌──────────────────┐    ┌─────────────────────┐    ┌────────────────┐ │
│  │ Auth Controller  │    │  Chat & RAG Engine  │    │ Docs Manager   │ │
│  │ (bcrypt / tokens)│    │  (LangGraph Agent)  │    │ (Parser/Chunk) │ │
│  └─────────┬────────┘    └──────────┬──────────┘    └────────┬───────┘ │
└────────────┼────────────────────────┼────────────────────────┼─────────┘
             ▼                        ▼                        ▼
┌──────────────────────┐   ┌─────────────────────┐   ┌───────────────────┐
│ Database (SQLite/PG) │   │ Vector Store Index  │   │ Google Drive API  │
│ - users              │   │ - FAISS / RuVector  │   │ Cloud Storage     │
│ - documents          │   │ - per-user vectors  │   │ - raw documents   │
│ - threads & messages │   │ - cached on disk    │   │ - vector backups  │
│ - refresh_tokens     │   │ - synced with Drive │   │ - workspace files │
└──────────────────────┘   └─────────────────────┘   └───────────────────┘
```

---

## 2. Multi-Tenant Relational Data Model

All operational entities enforce strict foreign keys to `users.id`:

```sql
-- 1. Users Table
CREATE TABLE users (
    id TEXT PRIMARY KEY,                   -- UUID v4
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. User Refresh Tokens
CREATE TABLE refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Persistent Documents (Google Drive Linked)
CREATE TABLE documents (
    id TEXT PRIMARY KEY,                   -- UUID v4
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    drive_file_id TEXT,                    -- Google Drive File ID
    drive_web_link TEXT,                   -- Direct View Link
    drive_folder_id TEXT,                  -- User's Drive Folder
    chunks_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ready',           -- 'uploading', 'ready', 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Chat Threads
CREATE TABLE threads (
    id TEXT PRIMARY KEY,                   -- UUID v4
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New Conversation',
    active_document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Thread Messages
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    tool_calls JSON,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. Google Drive Storage Layout

The Google Drive integration deterministically scopes assets under user namespaces:

```
Agent-Pilot Shared Drive Root/
└── users/
    └── {user_id}/
        ├── documents/
        │   └── {document_id}/
        │       ├── document.pdf
        │       └── metadata.json
        ├── vectors/
        │   └── {document_id}/
        │       ├── index.faiss
        │       └── index.pkl
        └── workspace/
            └── {thread_id}/
                └── exported_artifacts.json
```

---

## 4. End-to-End Sequence Flows

### 4.1 Document Upload & Cloud Sync Flow
```
User (Browser)          FastAPI Backend         Google Drive API      Database (SQLite)
      │                        │                        │                    │
      ├─ 1. POST /document ───►│                        │                    │
      │   (file + JWT)         ├─ 2. Validate user_id   │                    │
      │                        ├─ 3. Upload raw file ──►│                    │
      │                        │◄── drive_file_id ──────┤                    │
      │                        ├─ 4. Chunk & Embed      │                    │
      │                        ├─ 5. Upload Vector pkl─►│                    │
      │                        ├─ 6. INSERT document ───────────────────────►│
      │◄─ 200 OK (doc meta) ───┤                        │                    │
```

### 4.2 App Reload / Session Resume & Grounded RAG Query Flow
```
User (Browser)          FastAPI Backend         Local Cache / Drive   LangGraph Agent
      │                        │                        │                    │
      ├─ 1. Re-open browser ──►│                        │                    │
      │    GET /api/documents  ├─ 2. Query user docs ───────────────────────►│ (from DB)
      │◄── List of docs ───────┤                        │                    │
      │                        │                        │                    │
      ├─ 3. Select Doc & Ask ─►│                        │                    │
      │   "Summarize risks"    ├─ 4. Ensure index loaded│                    │
      │                        │    (if missing, fetch)─►                    │
      │                        ├─ 5. Retrieve Context ─►│                    │
      │                        ├─ 6. Generate Answer with Citations ────────►│
      │◄── SSE Stream Answer ──┤                        │                    │
```

---

## 5. Security & Isolation Envelope

1. **Authentication Guard**: Custom FastAPI dependency `get_current_user` decodes the JWT and yields `User(id, email)`. All protected route handlers inject `user: User = Depends(get_current_user)`.
2. **Path Traversal Protection**: Google Drive and local cache paths are strictly constructed using validated UUIDs:
   `os.path.join(STORAGE_BASE, str(user.id), str(doc.id))`.
3. **No Cross-Tenant Read/Write**: Every database query includes `WHERE user_id = :user_id`. An attempt to access another user's document returns HTTP 404 (or 403 Forbidden).
