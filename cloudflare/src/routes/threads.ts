import { Hono } from 'hono';
import {
  attachDocumentToThread,
  deleteThread,
  ensureThreadRegistered,
  getThreadActiveDocument,
  getThreadById,
  getThreads,
  updateThreadTitle,
} from '../db';
import { Env } from '../types';

export const threadsRouter = new Hono<{ Bindings: Env; Variables: { userId: string; userRole: string; userEmail: string } }>();

threadsRouter.get('/', async (c) => {
  const userId = c.get('userId') || 'guest';
  const threads = await getThreads(c.env.DB, userId);
  return c.json(threads);
});

threadsRouter.post('/', async (c) => {
  const userId = c.get('userId') || 'guest';
  const threadId = crypto.randomUUID();
  await ensureThreadRegistered(c.env.DB, threadId, userId, 'New chat');
  return c.json({ id: threadId, title: 'New chat' }, 201);
});

threadsRouter.get('/:id', async (c) => {
  const userId = c.get('userId') || 'guest';
  const id = c.req.param('id');
  const thread = await getThreadById(c.env.DB, id, userId);
  if (!thread) {
    return c.json({ detail: 'Thread not found or access denied.' }, 404);
  }
  return c.json(thread);
});

threadsRouter.patch('/:id', async (c) => {
  const userId = c.get('userId') || 'guest';
  const id = c.req.param('id');
  const body = await c.req.json().catch(() => ({}));
  const title = (body.title || '').trim();

  if (!title) {
    return c.json({ detail: 'Title cannot be empty.' }, 422);
  }

  const ok = await updateThreadTitle(c.env.DB, id, userId, title);
  if (!ok) {
    return c.json({ detail: 'Thread not found or access denied.' }, 404);
  }
  return c.json({ id, title });
});

threadsRouter.delete('/:id', async (c) => {
  const userId = c.get('userId') || 'guest';
  const id = c.req.param('id');
  const ok = await deleteThread(c.env.DB, id, userId);
  if (!ok) {
    return c.json({ detail: 'Thread not found or already deleted.' }, 404);
  }
  return c.json({ deleted: true, thread_id: id });
});

threadsRouter.get('/:id/document', async (c) => {
  const id = c.req.param('id');
  const doc = await getThreadActiveDocument(c.env.DB, id);
  if (!doc) {
    return c.json({ attached: false, document: null });
  }
  return c.json({
    attached: true,
    document: {
      ...doc,
      chunks_count: doc.chunks_count || 1,
      chunks: doc.chunks_count || 1,
    },
  });
});

threadsRouter.post('/:tid/documents/:did/attach', async (c) => {
  const userId = c.get('userId') || 'guest';
  const threadId = c.req.param('tid');
  const docId = c.req.param('did');

  await attachDocumentToThread(c.env.DB, threadId, docId, userId);
  const doc = await getThreadActiveDocument(c.env.DB, threadId);

  return c.json({
    attached: true,
    thread_id: threadId,
    doc_id: docId,
    document: doc,
    chunks_count: doc?.chunks_count || 1,
  });
});
