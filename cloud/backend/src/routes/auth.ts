import { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import {
  createSession,
  destroySession,
  destroyTrustedOwnerSessions,
  getSession,
  loginOwner,
  sessionCookieMaxAgeSeconds,
  type Session,
} from '../auth';
import { requireAuthCsrf, requireOrigin, requireOwnerCsrf } from '../guards';
import { config } from '../config';
import { productionIrControlEnabled } from '../mqtt_bridge';

function setSessionCookie(reply: FastifyReply, sessionId: string, expiresAt: number): void {
  reply.setCookie('sid', sessionId, {
    httpOnly: true,
    sameSite: 'strict',
    path: '/',
    secure: process.env.NODE_ENV === 'production',
    maxAge: sessionCookieMaxAgeSeconds(expiresAt),
  });
}

function trustedLabelFromRequest(req: FastifyRequest): string {
  const ua = req.headers['user-agent'];
  const value = Array.isArray(ua) ? ua[0] : ua;
  return String(value || 'trusted device').slice(0, 120);
}

function irControlForSession(session: Session | null): 'armed' | 'disabled' {
  return session?.role === 'owner' && session.trusted && productionIrControlEnabled()
    ? 'armed'
    : 'disabled';
}

function sessionPayload(session: Session) {
  return {
    authenticated: true,
    user: session.user,
    role: session.role,
    trusted: session.trusted,
    // 长期有效信任：trusted_persistent=true 且 trusted_expires_at=null。
    // 仅临时信任（expiresAt>0）才返回具体到期时间。
    trusted_persistent: session.trusted ? session.persistent : false,
    trusted_expires_at: session.trusted && !session.persistent && session.expiresAt > 0 ? session.expiresAt : null,
    trusted_label: session.trustedLabel || null,
    csrf: session.csrf,
    ir_control: irControlForSession(session),
  };
}

async function createGuestSession(reply: FastifyReply) {
  const created = await createSession();
  setSessionCookie(reply, created.sessionId, created.expiresAt);
  return getSession(created.sessionId);
}

export async function registerAuthRoutes(fastify: FastifyInstance): Promise<void> {
  fastify.post('/api/auth/login', { config: { rateLimit: { max: 5, timeWindow: '1 minute' } } }, async (req, reply) => {
    if (!config.IR_OWNER_PASSWORD) {
      reply.code(410).send({ error: 'login_disabled', detail: 'Owner login not configured' });
      return;
    }
    const body = (req.body ?? {}) as { username?: string; password?: string };
    const password = typeof body.password === 'string' ? body.password : '';
    const result = await loginOwner(password, { trustedLabel: trustedLabelFromRequest(req) });
    if (!result) {
      reply.code(401).send({ error: 'invalid_credentials' });
      return;
    }
    setSessionCookie(reply, result.sessionId, result.expiresAt);
    reply.send({
      ok: true,
      authenticated: true,
      user: result.user,
      role: 'owner',
      trusted: true,
      trusted_persistent: result.persistent,
      trusted_expires_at: !result.persistent && result.expiresAt > 0 ? result.expiresAt : null,
      trusted_label: result.trustedLabel || null,
      csrf: result.csrf,
      ir_control: productionIrControlEnabled() ? 'armed' : 'disabled',
    });
  });

  fastify.post('/api/auth/logout', { preHandler: [requireOrigin, requireAuthCsrf] }, async (req, reply) => {
    const sid = req.cookies?.sid;
    destroySession(sid);
    reply.clearCookie('sid', { path: '/' });
    if (config.ACCESS_MODE === 'public_guest') {
      await createGuestSession(reply);
    }
    reply.send({ ok: true });
  });

  fastify.post('/api/auth/trusted-device/revoke', { preHandler: [requireOrigin, requireOwnerCsrf] }, async (req, reply) => {
    const sid = req.cookies?.sid;
    destroySession(sid);
    reply.clearCookie('sid', { path: '/' });
    if (config.ACCESS_MODE === 'public_guest') {
      await createGuestSession(reply);
    }
    reply.send({ ok: true, revoked: 1 });
  });

  fastify.post('/api/auth/trusted-devices/revoke-all', { preHandler: [requireOrigin, requireOwnerCsrf] }, async (_req, reply) => {
    const revoked = destroyTrustedOwnerSessions();
    reply.clearCookie('sid', { path: '/' });
    if (config.ACCESS_MODE === 'public_guest') {
      await createGuestSession(reply);
    }
    reply.send({ ok: true, revoked });
  });

  fastify.get('/api/auth/session', async (req, reply) => {
    const sid = req.cookies?.sid;
    const session = sid ? getSession(sid) : null;
    if (session) {
      // 长期有效受信任会话：滚动续期浏览器 Cookie（同一 sid 重设 maxAge，
      // 不创建新会话记录，不产生重复设备行）。服务端记录本身无固定到期，
      // 撤销权始终在服务端（revoke 接口 / 密码指纹变化）。
      if (session.persistent && sid) {
        setSessionCookie(reply, sid, 0);
      }
      reply.send(sessionPayload(session));
      return;
    }
    if (config.ACCESS_MODE === 'public_guest') {
      const guest = await createGuestSession(reply);
      if (guest) {
        reply.send(sessionPayload(guest));
        return;
      }
    }
    reply.send({ authenticated: false, trusted: false, ir_control: 'disabled' });
  });
}
