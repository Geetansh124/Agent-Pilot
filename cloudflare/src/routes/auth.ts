import { Hono } from 'hono';
import {
  createAccessToken,
  generateRefreshToken,
  hashPassword,
  hashToken,
  verifyGoogleCredential,
  verifyPassword,
} from '../crypto';
import {
  createUser,
  getUserByEmail,
  getUserById,
  revokeAllUserRefreshTokens,
  storeRefreshToken,
  verifyAndConsumeRefreshToken,
} from '../db';
import { Env } from '../types';

export const authRouter = new Hono<{ Bindings: Env; Variables: { userId: string; userRole: string; userEmail: string } }>();

const EMAIL_REGEX = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

authRouter.post('/register', async (c) => {
  const body = await c.req.json().catch(() => ({}));
  const email = (body.email || '').trim().toLowerCase();
  const password = body.password || '';
  const fullName = (body.full_name || '').trim();

  if (!email || !EMAIL_REGEX.test(email)) {
    return c.json({ detail: 'Valid email address is required.' }, 422);
  }
  if (!password || password.length < 6) {
    return c.json({ detail: 'Password must be at least 6 characters long.' }, 422);
  }

  const existing = await getUserByEmail(c.env.DB, email);
  if (existing) {
    return c.json({ detail: `An account with email '${email}' already exists.` }, 409);
  }

  const { hash, salt } = await hashPassword(password);
  const userId = crypto.randomUUID();

  const user = await createUser(c.env.DB, {
    id: userId,
    email,
    hashed_password: hash,
    salt,
    full_name: fullName || null,
    role: 'user',
    provider: 'email',
  });

  const secret = c.env.JWT_SECRET || 'agent-pilot-jwt-edge-secret-cloudflare-production-2026-key';
  const accessToken = await createAccessToken({ sub: user.id, email: user.email, role: user.role }, secret, 3600);
  const rawRefreshToken = generateRefreshToken();
  const tokenHash = await hashToken(rawRefreshToken);
  const expiresAt = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString();

  await storeRefreshToken(c.env.DB, user.id, tokenHash, expiresAt);

  return c.json({
    user: {
      id: user.id,
      email: user.email,
      full_name: user.full_name,
      avatar_url: user.avatar_url,
      role: user.role,
      created_at: user.created_at,
    },
    access_token: accessToken,
    refresh_token: rawRefreshToken,
    token_type: 'bearer',
    expires_in: 3600,
  }, 201);
});

authRouter.post('/login', async (c) => {
  const body = await c.req.json().catch(() => ({}));
  const email = (body.email || '').trim().toLowerCase();
  const password = body.password || '';

  if (!email || !password) {
    return c.json({ detail: 'Email and password are required.' }, 422);
  }

  const user = await getUserByEmail(c.env.DB, email);
  if (!user || user.hashed_password === 'disabled') {
    return c.json({ detail: 'Invalid credentials.' }, 401);
  }

  const isValid = await verifyPassword(password, user.hashed_password, user.salt);
  if (!isValid) {
    return c.json({ detail: 'Invalid credentials.' }, 401);
  }

  const secret = c.env.JWT_SECRET || 'agent-pilot-jwt-edge-secret-cloudflare-production-2026-key';
  const accessToken = await createAccessToken({ sub: user.id, email: user.email, role: user.role }, secret, 3600);
  const rawRefreshToken = generateRefreshToken();
  const tokenHash = await hashToken(rawRefreshToken);
  const expiresAt = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString();

  await storeRefreshToken(c.env.DB, user.id, tokenHash, expiresAt);

  return c.json({
    user: {
      id: user.id,
      email: user.email,
      full_name: user.full_name,
      avatar_url: user.avatar_url,
      role: user.role,
      created_at: user.created_at,
    },
    access_token: accessToken,
    refresh_token: rawRefreshToken,
    token_type: 'bearer',
    expires_in: 3600,
  });
});

authRouter.post('/google', async (c) => {
  const body = await c.req.json().catch(() => ({}));
  const credential = body.credential;

  if (!credential) {
    return c.json({ detail: 'Missing Google credential token.' }, 422);
  }

  const googleData = await verifyGoogleCredential(credential, c.env.GOOGLE_CLIENT_ID);
  if (!googleData || !googleData.email) {
    return c.json({ detail: 'Invalid Google OAuth credential.' }, 401);
  }

  let user = await getUserByEmail(c.env.DB, googleData.email);
  if (!user) {
    user = await createUser(c.env.DB, {
      id: crypto.randomUUID(),
      email: googleData.email,
      full_name: googleData.name || null,
      avatar_url: googleData.picture || null,
      role: 'user',
      provider: 'google',
    });
  } else if (googleData.picture && (!user.avatar_url || user.avatar_url !== googleData.picture)) {
    await c.env.DB.prepare('UPDATE users SET avatar_url = ? WHERE id = ?')
      .bind(googleData.picture, user.id)
      .run();
    user.avatar_url = googleData.picture;
  }

  const secret = c.env.JWT_SECRET || 'agent-pilot-jwt-edge-secret-cloudflare-production-2026-key';
  const accessToken = await createAccessToken({ sub: user.id, email: user.email, role: user.role }, secret, 3600);
  const rawRefreshToken = generateRefreshToken();
  const tokenHash = await hashToken(rawRefreshToken);
  const expiresAt = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString();

  await storeRefreshToken(c.env.DB, user.id, tokenHash, expiresAt);

  return c.json({
    user: {
      id: user.id,
      email: user.email,
      full_name: user.full_name,
      avatar_url: user.avatar_url,
      role: user.role,
      created_at: user.created_at,
    },
    access_token: accessToken,
    refresh_token: rawRefreshToken,
    token_type: 'bearer',
    expires_in: 3600,
  });
});

authRouter.get('/me', async (c) => {
  const userId = c.get('userId');
  if (!userId || userId === 'guest') {
    return c.json({
      id: 'guest',
      email: 'guest@agentpilot.local',
      full_name: 'Guest User',
      avatar_url: null,
      role: 'guest',
      created_at: new Date().toISOString(),
    });
  }

  const user = await getUserById(c.env.DB, userId);
  if (!user) {
    return c.json({ detail: 'User not found.' }, 404);
  }

  return c.json({
    id: user.id,
    email: user.email,
    full_name: user.full_name,
    avatar_url: user.avatar_url,
    role: user.role,
    created_at: user.created_at,
  });
});

authRouter.post('/refresh', async (c) => {
  const body = await c.req.json().catch(() => ({}));
  const rawRefreshToken = body.refresh_token;

  if (!rawRefreshToken) {
    return c.json({ detail: 'Missing refresh token.' }, 422);
  }

  const tokenHash = await hashToken(rawRefreshToken);
  const userId = await verifyAndConsumeRefreshToken(c.env.DB, tokenHash);

  if (!userId) {
    return c.json({ detail: 'Invalid or expired refresh token.' }, 401);
  }

  const user = await getUserById(c.env.DB, userId);
  if (!user) {
    return c.json({ detail: 'User associated with token no longer exists.' }, 401);
  }

  const secret = c.env.JWT_SECRET || 'agent-pilot-jwt-edge-secret-cloudflare-production-2026-key';
  const newAccessToken = await createAccessToken({ sub: user.id, email: user.email, role: user.role }, secret, 3600);
  const newRawRefreshToken = generateRefreshToken();
  const newTokenHash = await hashToken(newRawRefreshToken);
  const expiresAt = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString();

  await storeRefreshToken(c.env.DB, user.id, newTokenHash, expiresAt);

  return c.json({
    access_token: newAccessToken,
    refresh_token: newRawRefreshToken,
    token_type: 'bearer',
    expires_in: 3600,
  });
});

authRouter.post('/logout', async (c) => {
  const userId = c.get('userId');
  if (userId && userId !== 'guest') {
    await revokeAllUserRefreshTokens(c.env.DB, userId);
  }
  return c.json({ ok: true });
});
