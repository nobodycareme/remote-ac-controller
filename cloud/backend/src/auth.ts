import crypto from 'node:crypto';
import { v4 as uuid } from 'uuid';
import { DatabaseSync } from 'node:sqlite';
import { config } from './config';
import { log } from './logger';

export type SessionRole = 'owner' | 'guest';

export interface Session {
  id: string;       // session ID (sent as cookie)
  hash: string;     // SHA-256 hash of session ID (stored in DB)
  user: string;
  role: SessionRole; // 'owner' (authenticated with password) | 'guest' (anonymous)
  csrf: string;
  createdAt: number;
  lastAccess: number;
}

const TTL = config.SESSION_TTL_MIN * 60_000;

// Sessions use a DEDICATED connection to avoid any lock/contention with the
// high-frequency telemetry writer on the main `db` connection. WAL allows this
// read-mostly store to proceed concurrently with telemetry inserts.
let _sessionDb: DatabaseSync | null = null;
function sessionDb(): DatabaseSync {
  if (!_sessionDb) {
    _sessionDb = new DatabaseSync(config.DB_PATH);
    _sessionDb.exec('PRAGMA journal_mode = WAL');
    _sessionDb.exec('PRAGMA busy_timeout = 5000');
    _sessionDb.exec(
      `CREATE TABLE IF NOT EXISTS sessions (
        sid_hash TEXT PRIMARY KEY,
        user_name TEXT NOT NULL DEFAULT 'admin',
        role TEXT NOT NULL DEFAULT 'guest',
        csrf TEXT NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL,
        last_access INTEGER NOT NULL DEFAULT 0
      )`
    );
  }
  return _sessionDb;
}

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
    const db = sessionDb();
    return {
      insert: (s: Session) => {
        db.prepare('INSERT OR REPLACE INTO sessions(sid_hash, user_name, role, csrf, created_at, last_access) VALUES(?,?,?,?,?,?)')
          .run(s.hash, s.user, s.role, s.csrf, s.createdAt, s.lastAccess);
      },
      get: (hash: string) => {
        return db.prepare('SELECT sid_hash, user_name, role, csrf, created_at, last_access FROM sessions WHERE sid_hash=?')
          .get(hash) as any;
      },
      delete: (hash: string) => {
        db.prepare('DELETE FROM sessions WHERE sid_hash=?').run(hash);
      },
      touch: (hash: string, ts: number) => {
        db.prepare('UPDATE sessions SET last_access=? WHERE sid_hash=?').run(ts, hash);
      },
    };
  } catch {
    return null;
  }
}

export async function createSession(role: SessionRole = 'guest'): Promise<{ sessionId: string; csrf: string }> {
  await initPassword();
  const sessionId = uuid();
  const csrf = uuid();
  const hash = sessionHash(sessionId);
  const now = Date.now();
  const user = role === 'owner' ? config.IR_OWNER_USER : 'guest';
  const session: Session = { id: sessionId, hash, user, role, csrf, createdAt: now, lastAccess: now };

  const sdb = dbSessions();
  if (sdb) {
    sdb.insert(session);
  } else {
    memoryFallback.set(sessionId, session);
  }
  return { sessionId, csrf };
}

// Mint an owner session after successful password verification. Returns null if
// the configured owner password is empty (owner login is disabled).
export async function loginOwner(password: string): Promise<{ sessionId: string; csrf: string; user: string } | null> {
  await initPassword();
  if (!config.IR_OWNER_PASSWORD) {
    return null; // owner login disabled when no password configured
  }
  const ok = await verifyPassword(password);
  if (!ok) return null;
  const { sessionId, csrf } = await createSession('owner');
  return { sessionId, csrf, user: config.IR_OWNER_USER };
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
    // NOTE: last_access update + expired cleanup run on a background timer
    // (startSessionCleanup), NOT on the request hot path, to keep getSession read-only.
    try {
      sdb.touch(row.sid_hash, now);
    } catch { /* best-effort */ }
    const role = row.role === 'owner' ? 'owner' : 'guest';
    return { id: sessionId, hash: row.sid_hash, user: row.user_name, role, csrf: row.csrf, createdAt: row.created_at, lastAccess: now };
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

// Periodic cleanup of expired sessions — runs off the request path.
export function startSessionCleanup(intervalMs = 10 * 60_000): void {
  setInterval(() => {
    try {
      sessionDb().prepare('DELETE FROM sessions WHERE last_access < ? OR created_at < ?')
        .run(Date.now() - TTL, Date.now() - TTL);
    } catch { /* ignore */ }
  }, intervalMs).unref();
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
