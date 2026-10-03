-- Agent-Pilot D1 Schema Migration
-- Mirrors the existing SQLite schema from src/auth/database.py

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    salt TEXT NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    role TEXT DEFAULT 'user',
    provider TEXT DEFAULT 'email',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    r2_key TEXT,
    text_content TEXT,
    chunks_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ready',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New chat',
    active_document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    tool_calls TEXT,
    tools_used TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS thread_documents (
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    attached_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (thread_id, doc_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_threads_user ON threads(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, created_at);

-- Seed guest user
INSERT OR IGNORE INTO users (id, email, hashed_password, salt, full_name, role, provider)
VALUES ('guest', 'guest@agentpilot.local', 'disabled', 'disabled', 'Guest User', 'guest', 'system');
