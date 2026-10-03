import { StoredDocument, ThreadRow, UserRow, MessageRow } from './types';

export async function getUserByEmail(db: D1Database, email: string): Promise<UserRow | null> {
  const normalized = email.trim().toLowerCase();
  const row = await db
    .prepare('SELECT * FROM users WHERE LOWER(email) = LOWER(?) LIMIT 1')
    .bind(normalized)
    .first<UserRow>();
  return row || null;
}

export async function getUserById(db: D1Database, id: string): Promise<UserRow | null> {
  const row = await db
    .prepare('SELECT * FROM users WHERE id = ? LIMIT 1')
    .bind(id)
    .first<UserRow>();
  return row || null;
}

export async function createUser(
  db: D1Database,
  user: {
    id: string;
    email: string;
    hashed_password?: string;
    salt?: string;
    full_name?: string | null;
    avatar_url?: string | null;
    role?: string;
    provider?: string;
  }
): Promise<UserRow> {
  const normalized = user.email.trim().toLowerCase();
  const id = user.id || crypto.randomUUID();
  const hashed_password = user.hashed_password || 'disabled';
  const salt = user.salt || 'disabled';
  const full_name = user.full_name || null;
  const avatar_url = user.avatar_url || null;
  const role = user.role || 'user';
  const provider = user.provider || 'email';

  await db
    .prepare(
      `INSERT INTO users (id, email, hashed_password, salt, full_name, avatar_url, role, provider)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(id, normalized, hashed_password, salt, full_name, avatar_url, role, provider)
    .run();

  const created = await getUserById(db, id);
  if (!created) throw new Error('Failed to retrieve created user');
  return created;
}

export async function storeRefreshToken(
  db: D1Database,
  userId: string,
  tokenHash: string,
  expiresAt: string
): Promise<void> {
  const id = crypto.randomUUID();
  await db
    .prepare('INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at) VALUES (?, ?, ?, ?)')
    .bind(id, userId, tokenHash, expiresAt)
    .run();
}

export async function verifyAndConsumeRefreshToken(
  db: D1Database,
  tokenHash: string
): Promise<string | null> {
  const row = await db
    .prepare(
      `SELECT id, user_id, expires_at FROM refresh_tokens
       WHERE token_hash = ? AND expires_at > datetime('now')
       LIMIT 1`
    )
    .bind(tokenHash)
    .first<{ id: string; user_id: string; expires_at: string }>();

  if (!row) return null;

  // Consume (delete) the refresh token
  await db.prepare('DELETE FROM refresh_tokens WHERE id = ?').bind(row.id).run();
  return row.user_id;
}

export async function revokeAllUserRefreshTokens(db: D1Database, userId: string): Promise<void> {
  await db.prepare('DELETE FROM refresh_tokens WHERE user_id = ?').bind(userId).run();
}

export async function ensureUserExists(db: D1Database, userId: string): Promise<void> {
  if (userId === 'guest') {
    await db
      .prepare(
        `INSERT OR IGNORE INTO users (id, email, hashed_password, salt, full_name, role, provider)
         VALUES ('guest', 'guest@agentpilot.local', 'disabled', 'disabled', 'Guest User', 'guest', 'system')`
      )
      .run();
  }
}

// ---------------------------------------------------------------------------
// Threads
// ---------------------------------------------------------------------------

export async function getThreads(db: D1Database, userId: string): Promise<any[]> {
  await ensureUserExists(db, userId);

  const threadsResult = await db
    .prepare('SELECT id, title, updated_at FROM threads WHERE user_id = ? ORDER BY updated_at DESC')
    .bind(userId)
    .all<ThreadRow>();

  const threads = threadsResult.results || [];
  const result: any[] = [];

  for (const t of threads) {
    const msgsResult = await db
      .prepare('SELECT role, content FROM messages WHERE thread_id = ? ORDER BY created_at ASC')
      .bind(t.id)
      .all<{ role: string; content: string }>();

    const messages = msgsResult.results || [];
    result.push({
      id: t.id,
      title: t.title || 'New chat',
      messages,
    });
  }

  return result;
}

export async function getThreadById(
  db: D1Database,
  threadId: string,
  userId: string
): Promise<{ id: string; title: string; messages: any[]; document: StoredDocument | null } | null> {
  const thread = await db
    .prepare('SELECT * FROM threads WHERE id = ? AND (user_id = ? OR user_id = "guest") LIMIT 1')
    .bind(threadId, userId)
    .first<ThreadRow>();

  if (!thread) return null;

  const msgsResult = await db
    .prepare('SELECT role, content FROM messages WHERE thread_id = ? ORDER BY created_at ASC')
    .bind(threadId)
    .all<{ role: string; content: string }>();

  let activeDoc: StoredDocument | null = null;
  if (thread.active_document_id) {
    activeDoc = await db
      .prepare('SELECT * FROM documents WHERE id = ? LIMIT 1')
      .bind(thread.active_document_id)
      .first<StoredDocument>();
  }

  return {
    id: thread.id,
    title: thread.title,
    messages: msgsResult.results || [],
    document: activeDoc || null,
  };
}

export async function ensureThreadRegistered(
  db: D1Database,
  threadId: string,
  userId: string,
  title?: string
): Promise<void> {
  await ensureUserExists(db, userId);
  await db
    .prepare(
      `INSERT INTO threads (id, user_id, title)
       VALUES (?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET
         title = CASE WHEN threads.title IN ('New Conversation', 'New chat') AND excluded.title != 'New chat'
                      THEN excluded.title ELSE threads.title END,
         updated_at = datetime('now')`
    )
    .bind(threadId, userId, title || 'New chat')
    .run();
}

export async function updateThreadTitle(
  db: D1Database,
  threadId: string,
  userId: string,
  title: string
): Promise<boolean> {
  const res = await db
    .prepare('UPDATE threads SET title = ?, updated_at = datetime("now") WHERE id = ? AND (user_id = ? OR user_id = "guest")')
    .bind(title, threadId, userId)
    .run();
  return (res.meta?.changes ?? 0) > 0;
}

export async function deleteThread(
  db: D1Database,
  threadId: string,
  userId: string
): Promise<boolean> {
  const res = await db
    .prepare('DELETE FROM threads WHERE id = ? AND (user_id = ? OR user_id = "guest")')
    .bind(threadId, userId)
    .run();
  return (res.meta?.changes ?? 0) > 0;
}

export async function saveMessage(
  db: D1Database,
  threadId: string,
  role: 'user' | 'assistant' | 'system' | 'tool',
  content: string,
  toolCalls?: string,
  toolsUsed?: string
): Promise<void> {
  const id = crypto.randomUUID();
  await db
    .prepare(
      `INSERT INTO messages (id, thread_id, role, content, tool_calls, tools_used)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(id, threadId, role, content, toolCalls || null, toolsUsed || null)
    .run();

  await db
    .prepare('UPDATE threads SET updated_at = datetime("now") WHERE id = ?')
    .bind(threadId)
    .run();
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export async function listDocuments(db: D1Database, userId: string): Promise<StoredDocument[]> {
  await ensureUserExists(db, userId);
  const rows = await db
    .prepare('SELECT * FROM documents WHERE user_id = ? ORDER BY created_at DESC')
    .bind(userId)
    .all<StoredDocument>();
  return rows.results || [];
}

export async function getDocumentById(
  db: D1Database,
  docId: string,
  userId: string
): Promise<StoredDocument | null> {
  const doc = await db
    .prepare('SELECT * FROM documents WHERE id = ? AND (user_id = ? OR user_id = "guest") LIMIT 1')
    .bind(docId, userId)
    .first<StoredDocument>();
  return doc || null;
}

export async function saveDocument(
  db: D1Database,
  doc: {
    id: string;
    user_id: string;
    filename: string;
    mime_type: string;
    size_bytes: number;
    text_content?: string;
    chunks_count?: number;
    status?: string;
  }
): Promise<StoredDocument> {
  await ensureUserExists(db, doc.user_id);
  await db
    .prepare(
      `INSERT INTO documents (id, user_id, filename, mime_type, size_bytes, text_content, chunks_count, status)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      doc.id,
      doc.user_id,
      doc.filename,
      doc.mime_type,
      doc.size_bytes,
      doc.text_content || null,
      doc.chunks_count || 1,
      doc.status || 'ready'
    )
    .run();

  const saved = await getDocumentById(db, doc.id, doc.user_id);
  if (!saved) throw new Error('Failed to retrieve saved document');
  return saved;
}

export async function deleteDocument(
  db: D1Database,
  docId: string,
  userId: string
): Promise<boolean> {
  const res = await db
    .prepare('DELETE FROM documents WHERE id = ? AND (user_id = ? OR user_id = "guest")')
    .bind(docId, userId)
    .run();
  return (res.meta?.changes ?? 0) > 0;
}

export async function attachDocumentToThread(
  db: D1Database,
  threadId: string,
  docId: string,
  userId: string
): Promise<boolean> {
  await ensureThreadRegistered(db, threadId, userId);
  await db
    .prepare('UPDATE threads SET active_document_id = ?, updated_at = datetime("now") WHERE id = ?')
    .bind(docId, threadId)
    .run();

  await db
    .prepare(
      `INSERT OR REPLACE INTO thread_documents (thread_id, doc_id, attached_at)
       VALUES (?, ?, datetime('now'))`
    )
    .bind(threadId, docId)
    .run();

  return true;
}

export async function getThreadActiveDocument(
  db: D1Database,
  threadId: string
): Promise<StoredDocument | null> {
  const thread = await db
    .prepare('SELECT active_document_id FROM threads WHERE id = ? LIMIT 1')
    .bind(threadId)
    .first<{ active_document_id: string | null }>();

  if (!thread || !thread.active_document_id) return null;

  return await db
    .prepare('SELECT * FROM documents WHERE id = ? LIMIT 1')
    .bind(thread.active_document_id)
    .first<StoredDocument>();
}
