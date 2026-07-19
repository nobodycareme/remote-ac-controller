import { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { verifyPassword, createSession, destroySession, getSession } from '../auth';
import { requireAuthCsrf } from '../guards';
import { log } from '../logger';

const loginSchema = z.object({
  username: z.string().min(1),
  password: z.string().min(1),
});

export async function registerAuthRoutes(fastify: FastifyInstance): Promise<void> {
  // Login — issues httpOnly session cookie + returns CSRF token.
  fastify.post('/api/auth/login', { config: { rateLimit: { max: 10, timeWindow: '1 minute' } } }, async (req, reply) => {
    const parsed = loginSchema.safeParse(req.body);
    if (!parsed.success) {
      reply.code(400).send({ error: 'invalid_request' });
      return;
    }
    const { username, password } = parsed.data;
    if (!verifyPassword(password) || username !== (process.env.WEB_USER || 'admin')) {
      log.warn('login failed', { username });
      reply.code(401).send({ error: 'invalid_credentials' });
      return;
    }
    const { sessionId, csrf } = createSession();
    reply.setCookie('sid', sessionId, {
      httpOnly: true,
      sameSite: 'strict',
      path: '/',
      secure: process.env.NODE_ENV === 'production',
      maxAge: 60 * (Number(process.env.SESSION_TTL_MIN) || 480) * 60,
    });
    log.info('login ok', { username });
    reply.send({ ok: true, csrf, user: username });
  });

  // Logout — CSRF protected.
  fastify.post('/api/auth/logout', { preHandler: requireAuthCsrf }, async (req, reply) => {
    const sid = req.cookies?.sid;
    const s = sid ? getSession(sid) : null;
    if (s) destroySession(s.id);
    reply.clearCookie('sid', { path: '/' });
    reply.send({ ok: true });
  });

  // Session probe — tells frontend if logged in (and returns csrf if so).
  // Does NOT use requireAuth: returns 200 {authenticated:false} instead of 401.
  fastify.get('/api/auth/session', async (req, reply) => {
    const sid = req.cookies?.sid;
    const session = sid ? getSession(sid) : null;
    if (session) {
      reply.send({ authenticated: true, user: session.user, csrf: session.csrf });
    } else {
      reply.send({ authenticated: false });
    }
  });
}
