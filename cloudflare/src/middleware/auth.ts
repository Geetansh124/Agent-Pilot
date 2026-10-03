import { Context, Next } from 'hono';
import { verifyAccessToken } from '../crypto';
import { Env } from '../types';

export async function authMiddleware(c: Context<{ Bindings: Env; Variables: { userId: string; userRole: string; userEmail: string } }>, next: Next) {
  const authHeader = c.req.header('Authorization');
  const secret = c.env.JWT_SECRET || 'agent-pilot-jwt-edge-secret-cloudflare-production-2026-key';

  let userId = 'guest';
  let userRole = 'guest';
  let userEmail = 'guest@agentpilot.local';

  if (authHeader && authHeader.startsWith('Bearer ')) {
    const token = authHeader.slice(7).trim();
    const payload = await verifyAccessToken(token, secret);
    if (payload && payload.sub) {
      userId = String(payload.sub);
      userRole = String(payload.role || 'user');
      userEmail = String(payload.email || '');
    }
  }

  c.set('userId', userId);
  c.set('userRole', userRole);
  c.set('userEmail', userEmail);

  await next();
}

export async function requireAuth(c: Context<{ Bindings: Env; Variables: { userId: string; userRole: string; userEmail: string } }>, next: Next) {
  const userId = c.get('userId');
  if (!userId || userId === 'guest') {
    return c.json({ detail: 'Authentication required' }, 401);
  }
  await next();
}
