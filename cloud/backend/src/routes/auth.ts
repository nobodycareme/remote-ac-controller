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
    trusted_expires_at: session.trusted ? session.expiresAt : null,
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
      trusted_expires_at: result.expiresAt,
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
