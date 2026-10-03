import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { authMiddleware } from './middleware/auth';
import { authRouter } from './routes/auth';
import { chatRouter } from './routes/chat';
import { documentsRouter } from './routes/documents';
import { threadsRouter } from './routes/threads';
import { Env } from './types';

const app = new Hono<{ Bindings: Env; Variables: { userId: string; userRole: string; userEmail: string } }>();

// Enable CORS for all incoming requests (supports local frontend development & remote domains)
app.use(
  '*',
  cors({
    origin: (origin) => origin || '*',
    allowHeaders: ['Content-Type', 'Authorization', 'X-Requested-With'],
    allowMethods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    credentials: true,
  })
);

// Global health check
app.get('/health', (c) => {
  return c.json({
    status: 'ok',
    storage: {
      backend: 'd1',
      status: 'connected',
    },
    version: '1.2.0-cloudflare',
  });
});

// Apply JWT auth middleware to all /api/ routes
app.use('/api/*', authMiddleware);

// Mount API routers
app.route('/api/auth', authRouter);
app.route('/api/threads', threadsRouter);
app.route('/api/documents', documentsRouter);
app.route('/api/chat', chatRouter);

// Fallback for static assets (Single-Page Application frontend)
app.all('*', async (c) => {
  if (c.env.ASSETS) {
    return await c.env.ASSETS.fetch(c.req.raw);
  }
  return c.text('Not Found', 404);
});

export default app;
