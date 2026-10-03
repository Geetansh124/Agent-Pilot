import { Hono } from 'hono';
import {
  attachDocumentToThread,
  deleteDocument,
  listDocuments,
  saveDocument,
} from '../db';
import { Env } from '../types';

export const documentsRouter = new Hono<{ Bindings: Env; Variables: { userId: string; userRole: string; userEmail: string } }>();

documentsRouter.get('/', async (c) => {
  const userId = c.get('userId') || 'guest';
  const docs = await listDocuments(c.env.DB, userId);
  return c.json({ documents: docs, total: docs.length });
});

documentsRouter.post('/upload', async (c) => {
  const userId = c.get('userId') || 'guest';
  const formData = await c.req.formData().catch(() => null);

  if (!formData) {
    return c.json({ detail: 'Multipart form data is required.' }, 400);
  }

  const file = formData.get('file');
  const threadId = formData.get('thread_id') ? String(formData.get('thread_id')) : null;

  if (!file || typeof file === 'string') {
    return c.json({ detail: 'File payload is missing.' }, 400);
  }

  const fileObj = file as File;
  const filename = fileObj.name || 'document.txt';
  const sizeBytes = fileObj.size || 0;
  const mimeType = fileObj.type || 'application/octet-stream';

  let textContent = '';
  try {
    // If text, markdown, json, csv, etc.
    if (
      mimeType.startsWith('text/') ||
      filename.endsWith('.txt') ||
      filename.endsWith('.md') ||
      filename.endsWith('.json') ||
      filename.endsWith('.csv') ||
      filename.endsWith('.tsv')
    ) {
      textContent = await fileObj.text();
    } else {
      // For PDF or other files, extract printable text snippets or headers
      const arrayBuf = await fileObj.arrayBuffer();
      const bytes = new Uint8Array(arrayBuf);
      const str = new TextDecoder('utf-8').decode(bytes);
      // Clean non-printable characters for simple text indexing
      textContent = str.replace(/[^\x20-\x7E\t\r\n]/g, ' ').replace(/\s+/g, ' ').slice(0, 50000);
    }
  } catch (err) {
    console.warn('Text extraction warning:', err);
  }

  const chunksCount = Math.max(1, Math.ceil(textContent.length / 1000));
  const docId = crypto.randomUUID();

  const saved = await saveDocument(c.env.DB, {
    id: docId,
    user_id: userId,
    filename,
    mime_type: mimeType,
    size_bytes: sizeBytes,
    text_content: textContent,
    chunks_count: chunksCount,
    status: 'ready',
  });

  if (threadId) {
    await attachDocumentToThread(c.env.DB, threadId, docId, userId);
  }

  return c.json({
    ...saved,
    chunks: chunksCount,
    chunks_count: chunksCount,
  }, 201);
});

documentsRouter.delete('/:id', async (c) => {
  const userId = c.get('userId') || 'guest';
  const id = c.req.param('id');
  const ok = await deleteDocument(c.env.DB, id, userId);
  if (!ok) {
    return c.json({ detail: 'Document not found or access denied.' }, 404);
  }
  return c.json({ deleted: true, id });
});
