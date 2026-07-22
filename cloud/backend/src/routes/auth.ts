import { FastifyInstance } from 'fastify';
import { createSession, getSession, loginOwner } from '../auth';
import { requireAuthCsrf, requireOrigin } from '../guards';
import { config } from '../config';
import { log } from '../logger';

export async function registerAuthRoutes(fastify: FastifyInstance): Promise<void> {
  // Owner login — mints an 'owner' session used for privileged real-IR actions.
  // Available whenever an owner password is configured (IR_OWNER_PASSWORD non-empty),
  // even in public_guest mode. If no owner password is set, login is disabled.
  fastify.post('/api/auth/login', { config: { rateLimit: { max: 5, timeWindow: '1 minute' } } }, async (req, reply) => {
    if (!config.IR_OWNER_PASSWORD) {
      reply.code(410).send({ error: 'login_disabled', detail: 'Owner login not configured' });
      return;
    }
    const body = (req.body ?? {}) as { username?: string; password?: string };
    const password = typeof body.password === 'string' ? body.password : '';
    const result = await loginOwner(password);
    if (!result) {
      reply.code(401).send({ error: 'invalid_credentials' });
      return;
    }
    reply.setCookie('sid', result.sessionId, {
      httpOnly: true, sameSite: 'strict', path: '/',
      secure: process.env.NODE_ENV === 'production',
      maxAge: 60 * config.SESSION_TTL_MIN * 60,
    });
    reply.send({ ok: true, authenticated: true, user: result.user, role: 'owner', csrf: result.csrf, ir_control: config.WEB_REAL_IR_ENABLED ? 'armed' : 'disabled' });
  });

  // Logout — CSRF protected.
  fastify.post('/api/auth/logout', { preHandler: [requireOrigin, requireAuthCsrf] }, async (req, reply) => {
    reply.clearCookie('sid', { path: '/' });
    // Auto-create a fresh guest session immediately (public mode)
    if (config.ACCESS_MODE === 'public_guest') {
      const { sessionId } = await createSession();
      reply.setCookie('sid', sessionId, {
        httpOnly: true, sameSite: 'strict', path: '/',
        secure: process.env.NODE_ENV === 'production',
        maxAge: 60 * config.SESSION_TTL_MIN * 60,
      });
    }
    reply.send({ ok: true });
  });

  // Session probe — auto-creates guest session if public mode
  fastify.get('/api/auth/session', async (req, reply) => {
    const sid = req.cookies?.sid;
    const session = sid ? getSession(sid) : null;
    if (session) {
      reply.send({ authenticated: true, user: session.user, role: session.role, csrf: session.csrf, ir_control: config.WEB_REAL_IR_ENABLED ? 'armed' : 'disabled' });
      return;
    }
    // Public guest: auto-create
    if (config.ACCESS_MODE === 'public_guest') {
      const { sessionId, csrf } = await createSession();
      reply.setCookie('sid', sessionId, {
        httpOnly: true, sameSite: 'strict', path: '/',
        secure: process.env.NODE_ENV === 'production',
        maxAge: 60 * config.SESSION_TTL_MIN * 60,
      });
      reply.send({ authenticated: true, user: 'guest', role: 'guest', csrf });
      return;
    }
    reply.send({ authenticated: false });
  });
}
