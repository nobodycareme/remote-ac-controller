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
  /**
   * 到期时间（ms epoch）。
   * 0 = 长期有效（persistent trust）：不因固定日期失效，仅由服务端撤销
   *（删行 / revoke 接口 / 密码指纹变化）终止。>0 = 临时信任，到点即失效。
   */
  expiresAt: number;
  /** true 表示该会话为长期有效受信任会话（expiresAt=0 的语义化标志）。 */
  persistent: boolean;
}

/** 长期信任的浏览器 Cookie 滚动续期窗口（每次合法访问刷新一次）。 */
export function trustedCookieRollingMaxAgeSeconds(): number {
  return Math.max(1, Number(config.TRUSTED_OWNER_SESSION_TTL_DAYS || 0)) * 86_400;
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
  // expiresAt=0 → 长期有效会话：Cookie 采用滚动续期窗口（TTL 天），
  // 每次 /api/auth/session 命中后由路由层重设 Cookie 实现续期。
  if (expiresAt === 0) return trustedCookieRollingMaxAgeSeconds();
  return Math.max(1, Math.floor((expiresAt - now) / 1000));
}

function normalizeLabel(label?: string): string {
  return String(label ?? '').trim().slice(0, 120);
}

function ownerCredentialFingerprint(): string {
  return crypto.createHash('sha256')
    .update(`web_user=${config.WEB_USER || ''}|web_password=${config.WEB_PASSWORD || ''}`)
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
  const parts = stored.split(':');
  if (parts.length !== 2 || !/^[0-9a-f]{32,}$/i.test(parts[0]) || !/^[0-9a-f]{128}$/i.test(parts[1])) {
    return Promise.resolve(false);
  }
  const expected = Buffer.from(parts[1], 'hex');
  return new Promise((resolve) => {
    crypto.scrypt(password, parts[0], expected.length, (err, derivedKey) => {
      resolve(!err && crypto.timingSafeEqual(expected, derivedKey));
    });
  });
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
  if (!config.WEB_PASSWORD || !password) return false;
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
  persistent: boolean;
}> {
  await initPassword();
  const sessionId = uuid();
  const csrf = uuid();
  const hash = sessionHash(sessionId);
  const now = Date.now();
  const user = role === 'owner' ? config.WEB_USER : 'guest';
  // Owner 受信任会话 = 长期有效（expiresAt=0 哨兵）：不因固定日期自动失效。
  // 撤销途径：移除本机/全部信任（删行）、密码指纹变化（getSession/cleanup 删行）。
  // Guest 仍为短期会话（SESSION_TTL_MIN）。
  const expiresAt = role === 'owner' ? 0 : now + sessionTtlMs(role);
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
    persistent: role === 'owner',
  };

  const sdb = dbSessions();
  if (sdb) {
    sdb.insert(session);
  } else {
    memoryFallback.set(sessionId, session);
  }

  return { sessionId, csrf, role, user, trusted: role === 'owner', trustedLabel, expiresAt, persistent: role === 'owner' };
}

export async function loginOwner(
  password: string,
  opts: { trustedLabel?: string; username?: string } = {},
): Promise<{ sessionId: string; csrf: string; user: string; trusted: boolean; trustedLabel: string; expiresAt: number; persistent: boolean } | null> {
  if (!config.WEB_PASSWORD || (opts.username !== undefined && opts.username !== config.WEB_USER)) return null;
  const ok = await verifyPassword(password);
  if (!ok) return null;
  const { sessionId, csrf, trustedLabel, expiresAt, trusted, persistent } = await createSession('owner', opts);
  return { sessionId, csrf, user: config.WEB_USER, trusted, trustedLabel, expiresAt, persistent };
}

export function getSession(sessionId?: string): Session | null {
  if (!sessionId) return null;

  const sdb = dbSessions();
  if (sdb) {
    const row = sdb.get(sessionHash(sessionId));
    if (!row) return null;
    const now = Date.now();
    const rawExpires = Number(row.expires_at || 0);
    // owner + expires_at=0 → 长期有效（persistent）：不做固定日期判定。
    // guest + expires_at=0 → 兼容旧行：按 created_at + guest TTL 推算。
    const persistent = row.role === 'owner' && rawExpires === 0;
    const expiresAt = persistent
      ? 0
      : rawExpires > 0
        ? rawExpires
        : Number(row.created_at || 0) + sessionTtlMs(row.role === 'owner' ? 'owner' : 'guest');
    if (!persistent && expiresAt <= now) {
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
      persistent,
    };
  }

  const s = memoryFallback.get(sessionId);
  if (!s) return null;
  const now = Date.now();
  const persistent = s.role === 'owner' && s.expiresAt === 0;
  const expiresAt = persistent ? 0 : (s.expiresAt || (s.createdAt + sessionTtlMs(s.role)));
  if (!persistent && expiresAt <= now) {
    memoryFallback.delete(sessionId);
    return null;
  }
  s.lastAccess = now;
  return s;
}

export function startSessionCleanup(intervalMs = 10 * 60_000): void {
  setInterval(() => {
    try {
      // 注意：expires_at=0 对 owner 表示"长期有效"，绝不能按 guest TTL 误删；
      // 只有非 owner 的 expires_at=0 旧行才按 guest TTL 清理。
      // owner 行的唯一自动失效途径是密码指纹变化（第三分支）。
      sessionDb().prepare(`DELETE FROM sessions
        WHERE (expires_at > 0 AND expires_at <= ?)
           OR (expires_at = 0 AND role <> 'owner' AND created_at < ?)
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
