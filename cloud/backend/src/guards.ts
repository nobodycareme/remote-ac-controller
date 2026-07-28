import { FastifyRequest, FastifyReply } from 'fastify';
import { config } from './config';
import { getSession, createSession, sessionCookieMaxAgeSeconds, validateCsrf } from './auth';
import { deny } from './reply_utils';

const ALLOWED_ORIGIN_SET = new Set(
  (config.ALLOWED_ORIGINS || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
);

function validOrigin(req: FastifyRequest): boolean {
  const origin = req.headers.origin;
  if (!origin) return false;
  return ALLOWED_ORIGIN_SET.has(origin);
}

// Reject requests with missing/invalid Origin for state-changing operations.
export async function requireOrigin(req: FastifyRequest, reply: FastifyReply): Promise<void> {
  if (!validOrigin(req)) {
    await deny(reply, 403, 'ORIGIN_DENIED', '请求来源不被允许（Origin 校验失败）');
    return;
  }
}

// In public_guest mode: auto-create an anonymous guest session if no valid session exists.
async function ensureSession(req: FastifyRequest, reply: FastifyReply): Promise<any | null> {
  const sid = req.cookies?.sid;
  let session = sid ? getSession(sid) : null;
  if (session) {
    (req as any).session = session;
    return session;
  }
  if (config.ACCESS_MODE === 'public_guest') {
    const { sessionId, expiresAt } = await createSession();
    reply.setCookie('sid', sessionId, {
      httpOnly: true,
      sameSite: 'strict',
      path: '/',
      secure: process.env.NODE_ENV === 'production',
      maxAge: sessionCookieMaxAgeSeconds(expiresAt),
    });
    session = getSession(sessionId);
    if (session) {
      (req as any).session = session;
      return session;
    }
  }
  return null;
}

// Attach session to request; auto-create guest session in public mode.
export async function requireAuth(req: FastifyRequest, reply: FastifyReply): Promise<void> {
  const s = await ensureSession(req, reply);
  if (!s) {
    await deny(reply, 401, 'UNAUTHORIZED', '未登录或会话已失效，请重新登录');
    return;
  }
}

// Like requireAuth, plus CSRF token check for state-changing requests.
export async function requireAuthCsrf(req: FastifyRequest, reply: FastifyReply): Promise<void> {
  const s = await ensureSession(req, reply);
  if (!s) {
    await deny(reply, 401, 'UNAUTHORIZED', '未登录或会话已失效，请重新登录');
    return;
  }
  const header = req.headers['x-csrf-token'];
  const token = Array.isArray(header) ? header[0] : header;
  if (!validateCsrf(s, token)) {
    await deny(reply, 403, 'CSRF_INVALID', 'CSRF 令牌校验失败');
    return;
  }
}

export function getRequestSession(req: FastifyRequest): any | null {
  return (req as any).session ?? null;
}

// ── Owner-gated guard (Task §七/§八/§九) ─────────────────────────────────────
// Real-IR actions require an OWNER session (authenticated with password), a valid
// Origin, and a matching CSRF token. Guests (auto-created anonymous sessions),
// unauthenticated callers, CSRF mismatches, and invalid Origins are all denied.
// This guard does NOT auto-create a guest session — only an existing owner may pass.
export async function requireOwnerCsrf(req: FastifyRequest, reply: FastifyReply): Promise<void> {
  if (!validOrigin(req)) {
    await deny(reply, 403, 'ORIGIN_DENIED', '请求来源不被允许（Origin 校验失败）');
    return;
  }
  const sid = req.cookies?.sid;
  const session = sid ? getSession(sid) : null;
  if (!session) {
    await deny(reply, 401, 'SESSION_EXPIRED', '所有者会话缺失或已失效，请重新登录', { ir_control: 'disabled' });
    return;
  }
  if (session.role !== 'owner' || !session.trusted) {
    await deny(reply, 403, 'OWNER_REQUIRED', '真实红外操作需要所有者登录', { ir_control: 'disabled' });
    return;
  }
  const header = req.headers['x-csrf-token'];
  const token = Array.isArray(header) ? header[0] : header;
  if (!validateCsrf(session, token)) {
    await deny(reply, 403, 'CSRF_INVALID', 'CSRF 令牌校验失败', { ir_control: 'disabled' });
    return;
  }
  (req as any).session = session;
}
