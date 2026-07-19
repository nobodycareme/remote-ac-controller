import bcrypt from 'bcryptjs';
import { v4 as uuid } from 'uuid';
import { config } from './config';
import { log } from './logger';

export interface Session {
  id: string;
  user: string;
  csrf: string;
  createdAt: number;
}

const sessions = new Map<string, Session>();
const TTL = config.SESSION_TTL_MIN * 60_000;

export function verifyPassword(password: string): boolean {
  // constant-time compare via bcrypt (WEB_PASSWORD may be bcrypt hash or plaintext)
  const expected = config.WEB_PASSWORD;
  if (expected.startsWith('$2')) return bcrypt.compareSync(password, expected);
  return password === expected;
}

export function createSession(): { sessionId: string; csrf: string } {
  const sessionId = uuid();
  const csrf = uuid();
  sessions.set(sessionId, { id: sessionId, user: config.WEB_USER, csrf, createdAt: Date.now() });
  return { sessionId, csrf };
}

export function getSession(sessionId?: string): Session | null {
  if (!sessionId) return null;
  const s = sessions.get(sessionId);
  if (!s) return null;
  if (Date.now() - s.createdAt > TTL) {
    sessions.delete(sessionId);
    return null;
  }
  return s;
}

export function destroySession(sessionId?: string): void {
  if (sessionId) sessions.delete(sessionId);
}

export function validateCsrf(session: Session | null, headerToken?: string): boolean {
  if (!session || !headerToken) return false;
  return session.csrf === headerToken;
}
