import crypto from 'node:crypto';
import { v4 as uuid } from 'uuid';
import { config } from './config';
import { log } from './logger';
import { getDb } from './db';

export interface Session {
  id: string;       // session ID (sent as cookie)
  hash: string;     // SHA-256 hash of session ID (stored in DB)
  user: string;
  csrf: string;
  createdAt: number;
  lastAccess: number;
}

const TTL = config.SESSION_TTL_MIN * 60_000;

// ── Password ──────────────────────────────────────────
// Use Node.js built-in crypto.scrypt (no native module, no bcryptjs)

function scryptHash(password: string, salt: string): Promise<string> {
  return new Promise((resolve, reject) => {
    crypto.scrypt(password, salt, 64, (err, derivedKey) => {
      if (err) return reject(err);
      resolve(`${salt}:${derivedKey.toString('hex')}`);
    });
  });
}

function scryptVerify(password: string, stored: string): Promise<boolean> {
  const [salt, hash] = stored.split(':');
  return scryptHash(password, salt).then(h => h === stored);
}

let _passwordVerified = false;
let _storedHash: string | null = null;

async function initPassword(): Promise<void> {
  if (_passwordVerified) return;
  const expected = config.WEB_PASSWORD;
  if (expected.startsWith('$2')) {
    // Legacy bcrypt hash — migrate to scrypt on first successful login
    _storedHash = null; // Will be migrated
  } else if (expected.includes(':')) {
    // Already scrypt format: salt:hash
    _storedHash = expected;
  } else {
    // Plaintext — hash it once at startup
    const salt = crypto.randomBytes(16).toString('hex');
    _storedHash = await scryptHash(expected, salt);
    log.warn('auth using plaintext password; pre-hashing at startup');
  }
  _passwordVerified = true;
}

export async function verifyPassword(password: string): Promise<boolean> {
  await initPassword();
  if (_storedHash) {
    return scryptVerify(password, _storedHash);
  }
  // Legacy bcrypt fallback (one-time, then migrated)
  const bcrypt = await import('bcryptjs');
  if (bcrypt.compareSync(password, config.WEB_PASSWORD)) {
    const salt = crypto.randomBytes(16).toString('hex');
    _storedHash = await scryptHash(password, salt);
    log.info('password migrated from bcrypt to scrypt');
    return true;
  }
  return false;
}

// ── Session ───────────────────────────────────────────
// Session ID = UUID v4 (high entropy, 36 chars)
// DB stores SHA-256 hash of session ID (not the ID itself)
// Cookie = session ID only (HttpOnly, SameSite=Strict)

function sessionHash(sessionId: string): string {
  return crypto.createHash('sha256').update(sessionId).digest('hex');
}

const memoryFallback = new Map<string, Session>(); // Fallback when DB not available

function dbSessions() {
  try {
    const db = getDb();
    return {
      insert: (s: Session) => {
        db.prepare('INSERT OR REPLACE INTO sessions(sid_hash, user_name, csrf, created_at, last_access) VALUES(?,?,?,?,?)')
          .run(s.hash, s.user, s.csrf, s.createdAt, s.lastAccess);
      },
      get: (hash: string) => {
        return db.prepare('SELECT sid_hash, user_name, csrf, created_at, last_access FROM sessions WHERE sid_hash=?')
          .get(hash) as any;
      },
      delete: (hash: string) => {
        db.prepare('DELETE FROM sessions WHERE sid_hash=?').run(hash);
      },
      cleanExpired: () => {
        const cutoff = Date.now() - TTL;
        db.prepare('DELETE FROM sessions WHERE last_access < ?').run(cutoff);
      },
    };
  } catch {
    return null;
  }
}

export async function createSession(): Promise<{ sessionId: string; csrf: string }> {
  await initPassword();
  const sessionId = uuid();
  const csrf = uuid();
  const hash = sessionHash(sessionId);
  const now = Date.now();
  const session: Session = { id: sessionId, hash, user: config.WEB_USER, csrf, createdAt: now, lastAccess: now };

  const sdb = dbSessions();
  if (sdb) {
    sdb.insert(session);
  } else {
    memoryFallback.set(sessionId, session);
  }
  return { sessionId, csrf };
}

export function getSession(sessionId?: string): Session | null {
  if (!sessionId) return null;

  const sdb = dbSessions();
  if (sdb) {
    const row = sdb.get(sessionHash(sessionId));
    if (!row) return null;
    const now = Date.now();
    if (now - row.created_at > TTL) {
      sdb.delete(row.sid_hash);
      return null;
    }
    // Update last access
    sdb.cleanExpired();
    return { id: sessionId, hash: row.sid_hash, user: row.user_name, csrf: row.csrf, createdAt: row.created_at, lastAccess: now };
  }

  // Memory fallback
  const s = memoryFallback.get(sessionId);
  if (!s) return null;
  if (Date.now() - s.createdAt > TTL) {
    memoryFallback.delete(sessionId);
    return null;
  }
  s.lastAccess = Date.now();
  return s;
}

export function destroySession(sessionId?: string): void {
  if (!sessionId) return;
  const sdb = dbSessions();
  if (sdb) {
    sdb.delete(sessionHash(sessionId));
  }
  memoryFallback.delete(sessionId);
}

export function validateCsrf(session: Session | null, headerToken?: string): boolean {
  if (!session || !headerToken) return false;
  // Constant-time comparison
  try {
    return crypto.timingSafeEqual(
      Buffer.from(session.csrf),
      Buffer.from(headerToken)
    );
  } catch {
    return false;
  }
}
