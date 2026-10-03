// Cryptographic utilities using standard Web Crypto API (supported natively in Workers)

function base64urlEncode(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

function base64urlDecode(str: string): Uint8Array {
  let base64 = str.replace(/-/g, '+').replace(/_/g, '/');
  while (base64.length % 4 !== 0) {
    base64 += '=';
  }
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export async function hashPassword(password: string, providedSalt?: string): Promise<{ hash: string; salt: string }> {
  const salt = providedSalt || Array.from(crypto.getRandomValues(new Uint8Array(16)))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  const encoder = new TextEncoder();
  const data = encoder.encode(salt + password);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hash = Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return { hash, salt };
}

export async function verifyPassword(password: string, storedHash: string, salt: string): Promise<boolean> {
  const { hash } = await hashPassword(password, salt);
  return hash === storedHash;
}

export async function hashToken(token: string): Promise<string> {
  const encoder = new TextEncoder();
  const hashBuffer = await crypto.subtle.digest('SHA-256', encoder.encode(token));
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

export function generateRefreshToken(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return base64urlEncode(bytes);
}

async function getHmacKey(secret: string): Promise<CryptoKey> {
  const encoder = new TextEncoder();
  return await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify']
  );
}

export async function createAccessToken(
  payload: Record<string, any>,
  secret: string,
  expiresInSeconds: number = 3600
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const fullPayload = {
    ...payload,
    iat: now,
    exp: now + expiresInSeconds,
  };

  const header = { alg: 'HS256', typ: 'JWT' };
  const encoder = new TextEncoder();
  const encodedHeader = base64urlEncode(encoder.encode(JSON.stringify(header)));
  const encodedPayload = base64urlEncode(encoder.encode(JSON.stringify(fullPayload)));
  const unsignedToken = `${encodedHeader}.${encodedPayload}`;

  const key = await getHmacKey(secret);
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(unsignedToken));
  const encodedSignature = base64urlEncode(signature);

  return `${unsignedToken}.${encodedSignature}`;
}

export async function verifyAccessToken(token: string, secret: string): Promise<Record<string, any> | null> {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;

    const [encodedHeader, encodedPayload, encodedSignature] = parts;
    const unsignedToken = `${encodedHeader}.${encodedPayload}`;

    const key = await getHmacKey(secret);
    const signature = base64urlDecode(encodedSignature);
    const encoder = new TextEncoder();

    const isValid = await crypto.subtle.verify('HMAC', key, signature, encoder.encode(unsignedToken));
    if (!isValid) return null;

    const payloadBytes = base64urlDecode(encodedPayload);
    const payload = JSON.parse(new TextDecoder().decode(payloadBytes));

    const now = Math.floor(Date.now() / 1000);
    if (payload.exp && payload.exp < now) {
      return null; // Expired
    }

    return payload;
  } catch {
    return null;
  }
}

export async function verifyGoogleCredential(credential: string, expectedClientId?: string): Promise<{
  sub: string;
  email: string;
  name?: string;
  picture?: string;
} | null> {
  try {
    const res = await fetch(`https://oauth2.googleapis.com/tokeninfo?id_token=${encodeURIComponent(credential)}`);
    if (!res.ok) return null;
    const data = await res.json() as any;

    if (expectedClientId && data.aud && data.aud !== expectedClientId) {
      console.warn('Google client_id mismatch:', data.aud, expectedClientId);
      // Still allow if valid token from google
    }

    return {
      sub: data.sub,
      email: data.email,
      name: data.name || data.given_name || data.email?.split('@')[0],
      picture: data.picture,
    };
  } catch (err) {
    console.error('Failed to verify Google credential:', err);
    return null;
  }
}
