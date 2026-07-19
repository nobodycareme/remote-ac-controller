// Auth pre-handlers: session cookie validation + CSRF double-submit check.
import { FastifyRequest, FastifyReply } from 'fastify';
import { getSession, validateCsrf, Session } from './auth';

function sessionFromReq(req: FastifyRequest): Session | null {
  const sid = req.cookies?.sid;
  return getSession(sid);
}

// Attach session to request; reject if missing/expired.
export function requireAuth(req: FastifyRequest, reply: FastifyReply, done: (err?: Error) => void): void {
  const s = sessionFromReq(req);
  if (!s) {
    reply.code(401).send({ error: 'unauthorized' });
    return;
  }
  (req as unknown as { session: Session }).session = s;
  done();
}

// Like requireAuth, plus CSRF token check for state-changing requests.
export function requireAuthCsrf(req: FastifyRequest, reply: FastifyReply, done: (err?: Error) => void): void {
  const s = sessionFromReq(req);
  if (!s) {
    reply.code(401).send({ error: 'unauthorized' });
    return;
  }
  const header = req.headers['x-csrf-token'];
  const token = Array.isArray(header) ? header[0] : header;
  if (!validateCsrf(s, token)) {
    reply.code(403).send({ error: 'csrf_token_mismatch' });
    return;
  }
  (req as unknown as { session: Session }).session = s;
  done();
}

export function getRequestSession(req: FastifyRequest): Session | null {
  return (req as unknown as { session?: Session }).session ?? null;
}
