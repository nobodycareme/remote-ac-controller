import crypto from 'node:crypto';
import { v4 as uuid } from 'uuid';
import { DatabaseSync } from 'node:sqlite';
import { config } from './config';
import { log } from './logger';

export type SessionRole = 'owner' | 'guest';

export interface Session {
  id: string;
  hash: string;
  user: string;
  role: SessionRole;
  trusted: boolean;
  trustedLabel: string;
  ownerPasswordFingerprint: string;
  csrf: string;
  createdAt: number;
  lastAccess: number;
  expiresAt: number;
}

function guestSessionTtlMs(): number {
  return Math.max(1, Number(config.SESSION_TTL_MIN || 0)) * 60_000;
}

function trustedOwnerSessionTtlMs(): number {
  return Math.max(1, Number(config.TRUSTED_OWNER_SESSION_TTL_DAYS || 0)) * 86_400_000;
}

function sessionTtlMs(role: SessionRole): number {
  return role === 'owner' ? trustedOwnerSessionTtlMs() : guestSessionTtlMs();
}

export function sessionCookieMaxAgeSeconds(expiresAt: number, now = Date.now()): number {
  return Math.max(1, Math.floor((expiresAt - now) / 1000));
}

function normalizeLabel(label?: string): string {
  return String(label ?? '').trim().slice(0, 120);
}

function ownerCredentialFingerprint(): string {
  return crypto.createHash('sha256')
    .update([
      `web_password=${config.WEB_PASSWORD || ''}`,
      `ir_owner_password=${config.IR_OWNER_PASSWORD || ''}`,
    ].join('|'))
    .digest('hex');
}

// Sessions use a dedicated connection to avoid lock/contention with telemetry.
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
        trusted_label TEXT NOT NULL DEFAULT '',
        owner_password_fingerprint TEXT NOT NULL DEFAULT '',
        csrf TEXT NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL DEFAULT 0,
        last_access INTEGER NOT NULL DEFAULT 0
      )`
    );
    for (const col of [
      "role TEXT NOT NULL DEFAULT 'guest'",
      "trusted_label TEXT NOT NULL DEFAULT ''",
      "owner_password_fingerprint TEXT NOT NULL DEFAULT ''",
      'expires_at INTEGER NOT NULL DEFAULT 0',
    ]) {
      try {
        _sessionDb.exec(`ALTER TABLE sessions ADD COLUMN ${col}`);
      } catch (e: any) {
        if (!/duplicate column/i.test(e?.message ?? '')) {
          log.warn('auth session migration skip', { col: col.split(' ')[0], err: e?.message });
        }
      }
    }
    try {
      _sessionDb.exec('CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)');
      _sessionDb.exec('CREATE INDEX IF NOT EXISTS idx_sessions_role ON sessions(role, owner_password_fingerprint)');
    } catch {
      /* ignore */
    }
  }
  return _sessionDb;
}

function scryptHash(password: string, salt: string): Promise<string> {
  return new Promise((resolve, reject) => {
    crypto.scrypt(password, salt, 64, (err, derivedKey) => {
      if (err) return reject(err);
      resolve(`${salt}:${derivedKey.toString('hex')}`);
    });
  });
}

function scryptVerify(password: string, stored: string): Promise<boolean> {
  const [salt] = stored.split(':');
  return scryptHash(password, salt).then((h) => h === stored);
}

let _passwordSourceKey: string | null = null;
let _storedHash: string | null = null;

async function initPassword(): Promise<void> {
  const expected = config.WEB_PASSWORD;
  if (_passwordSourceKey === expected) return;
  _passwordSourceKey = expected;
  _storedHash = null;
  if (expected.startsWith('$2')) {
    // Legacy bcrypt hash; migrate on successful login.
    _storedHash = null;
  } else if (expected.includes(':')) {
    // Already scrypt format: salt:hash.
    _storedHash = expected;
  } else {
    const salt = crypto.randomBytes(16).toString('hex');
    _storedHash = await scryptHash(expected, salt);
    log.warn('auth using plaintext password; pre-hashing at startup');
  }
}

export async function verifyPassword(password: string): Promise<boolean> {
  await initPassword();
  if (_storedHash) {
    return scryptVerify(password, _storedHash);
  }
  const bcrypt = await import('bcryptjs');
  if (bcrypt.compareSync(password, config.WEB_PASSWORD)) {
    const salt = crypto.randomBytes(16).toString('hex');
    _storedHash = await scryptHash(password, salt);
    log.info('password migrated from bcrypt to scrypt');
    return true;
  }
  return false;
}

function sessionHash(sessionId: string): string {
  return crypto.createHash('sha256').update(sessionId).digest('hex');
}

const memoryFallback = new Map<string, Session>();

function dbSessions() {
  try {
    const db = sessionDb();
    return {
      insert: (s: Session) => {
        db.prepare(`INSERT OR REPLACE INTO sessions
          (sid_hash, user_name, role, trusted_label, owner_password_fingerprint, csrf, created_at, expires_at, last_access)
          VALUES (?,?,?,?,?,?,?,?,?)`).run(
          s.hash,
          s.user,
          s.role,
          s.trustedLabel,
          s.ownerPasswordFingerprint,
          s.csrf,
          s.createdAt,
          s.expiresAt,
          s.lastAccess,
        );
      },
      get: (hash: string) => db.prepare(`SELECT sid_hash, user_name, role, trusted_label, owner_password_fingerprint, csrf, created_at, expires_at, last_access
        FROM sessions WHERE sid_hash=?`).get(hash) as any,
      delete: (hash: string) => {
        db.prepare('DELETE FROM sessions WHERE sid_hash=?').run(hash);
      },
      touch: (hash: string, ts: number) => {
        db.prepare('UPDATE sessions SET last_access=? WHERE sid_hash=?').run(ts, hash);
      },
      updateOwnerFingerprint: (hash: string, fingerprint: string) => {
        db.prepare('UPDATE sessions SET owner_password_fingerprint=? WHERE sid_hash=?').run(fingerprint, hash);
      },
      deleteOwnerSessions: () => db.prepare("DELETE FROM sessions WHERE role='owner'").run(),
    };
  } catch {
    return null;
  }
}

export async function createSession(
  role: SessionRole = 'guest',
  opts: { trustedLabel?: string } = {},
): Promise<{
  sessionId: string;
  csrf: string;
  role: SessionRole;
  user: string;
  trusted: boolean;
  trustedLabel: string;
  expiresAt: number;
}> {
  await initPassword();
  const sessionId = uuid();
  const csrf = uuid();
  const hash = sessionHash(sessionId);
  const now = Date.now();
  const user = role === 'owner' ? config.IR_OWNER_USER : 'guest';
  const expiresAt = now + sessionTtlMs(role);
  const trustedLabel = role === 'owner' ? normalizeLabel(opts.trustedLabel) : '';
  const ownerPasswordFingerprint = role === 'owner' ? ownerCredentialFingerprint() : '';
  const session: Session = {
    id: sessionId,
    hash,
    user,
    role,
    trusted: role === 'owner',
    trustedLabel,
    ownerPasswordFingerprint,
    csrf,
    createdAt: now,
    lastAccess: now,
    expiresAt,
  };

  const sdb = dbSessions();
  if (sdb) {
    sdb.insert(session);
  } else {
    memoryFallback.set(sessionId, session);
  }

  return { sessionId, csrf, role, user, trusted: role === 'owner', trustedLabel, expiresAt };
}

export async function loginOwner(
  password: string,
  opts: { trustedLabel?: string } = {},
): Promise<{ sessionId: string; csrf: string; user: string; trusted: boolean; trustedLabel: string; expiresAt: number } | null> {
  await initPassword();
  if (!config.IR_OWNER_PASSWORD) {
    return null;
  }
  const ok = await verifyPassword(password);
  if (!ok) return null;
  const { sessionId, csrf, trustedLabel, expiresAt, trusted } = await createSession('owner', opts);
  return { sessionId, csrf, user: config.IR_OWNER_USER, trusted, trustedLabel, expiresAt };
}

export function getSession(sessionId?: string): Session | null {
  if (!sessionId) return null;

  const sdb = dbSessions();
  if (sdb) {
    const row = sdb.get(sessionHash(sessionId));
    if (!row) return null;
    const now = Date.now();
    const expiresAt = Number(row.expires_at || 0) > 0
      ? Number(row.expires_at)
      : Number(row.created_at || 0) + sessionTtlMs(row.role === 'owner' ? 'owner' : 'guest');
    if (expiresAt <= now) {
      sdb.delete(row.sid_hash);
      return null;
    }
    let ownerFingerprint = String(row.owner_password_fingerprint || '');
    if (row.role === 'owner') {
      const currentFingerprint = ownerCredentialFingerprint();
      if (ownerFingerprint && ownerFingerprint !== currentFingerprint) {
        sdb.delete(row.sid_hash);
        return null;
      }
      if (!ownerFingerprint) {
        ownerFingerprint = currentFingerprint;
        try {
          sdb.updateOwnerFingerprint(row.sid_hash, ownerFingerprint);
        } catch {
          /* ignore */
        }
      }
    }
    try {
      sdb.touch(row.sid_hash, now);
    } catch {
      /* best-effort */
    }
    const role = row.role === 'owner' ? 'owner' : 'guest';
    return {
      id: sessionId,
      hash: row.sid_hash,
      user: row.user_name,
      role,
      trusted: role === 'owner',
      trustedLabel: String(row.trusted_label || ''),
      ownerPasswordFingerprint: ownerFingerprint,
      csrf: row.csrf,
      createdAt: row.created_at,
      lastAccess: now,
      expiresAt,
    };
  }

  const s = memoryFallback.get(sessionId);
  if (!s) return null;
  const now = Date.now();
  const expiresAt = s.expiresAt || (s.createdAt + sessionTtlMs(s.role));
  if (expiresAt <= now) {
    memoryFallback.delete(sessionId);
    return null;
  }
  s.lastAccess = now;
  return s;
}

export function startSessionCleanup(intervalMs = 10 * 60_000): void {
  setInterval(() => {
    try {
      sessionDb().prepare(`DELETE FROM sessions
        WHERE (expires_at > 0 AND expires_at <= ?)
           OR (expires_at = 0 AND created_at < ?)
           OR (role='owner' AND owner_password_fingerprint <> ? AND owner_password_fingerprint <> '')`)
        .run(Date.now(), Date.now() - guestSessionTtlMs(), ownerCredentialFingerprint());
    } catch {
      /* ignore */
    }
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

export function destroyTrustedOwnerSessions(): number {
  let changes = 0;
  try {
    const sdb = dbSessions();
    if (sdb) {
      changes = Number(sdb.deleteOwnerSessions().changes ?? 0);
    }
  } catch {
    /* ignore */
  }
  for (const [sid, session] of memoryFallback.entries()) {
    if (session.role === 'owner') {
      memoryFallback.delete(sid);
    }
  }
  return changes;
}

export function validateCsrf(session: Session | null, headerToken?: string): boolean {
  if (!session || !headerToken) return false;
  try {
    return crypto.timingSafeEqual(
      Buffer.from(session.csrf),
      Buffer.from(headerToken),
    );
  } catch {
    return false;
  }
}
