import { describe, it, expect, beforeEach } from 'vitest';
import bcrypt from 'bcryptjs';
import crypto from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { verifyPassword, createSession, getSession, destroySession, validateCsrf, loginOwner } from '../src/auth';
import { initDb } from '../src/db';
import { config } from '../src/config';

describe('auth', () => {
  beforeEach(async () => {
    await initDb();
    (config as any).IR_OWNER_PASSWORD = '';
    (config as any).WEB_PASSWORD = bcrypt.hashSync('test-admin-pass', 8);
  });

  it('verifyPassword accepts correct bcrypt password', async () => {
    expect(await verifyPassword('test-admin-pass')).toBe(true);
  });

  it('verifyPassword rejects wrong password', async () => {
    expect(await verifyPassword('nope')).toBe(false);
  });

  it('createSession defaults to an anonymous guest session', async () => {
    const created = await createSession();
    const s = getSession(created.sessionId);
    expect(s).not.toBeNull();
    expect(s!.csrf).toBe(created.csrf);
    expect(s!.user).toBe('guest');
    expect(s!.role).toBe('guest');
    expect(s!.trusted).toBe(false);
  });

  it('createSession("owner") mints a trusted owner session bound to IR_OWNER_USER', async () => {
    (config as any).IR_OWNER_PASSWORD = 'enabled';
    const created = await createSession('owner');
    const s = getSession(created.sessionId);
    expect(s).not.toBeNull();
    expect(s!.csrf).toBe(created.csrf);
    expect(s!.user).toBe('admin');
    expect(s!.role).toBe('owner');
    expect(s!.trusted).toBe(true);
    expect(s!.expiresAt).toBeGreaterThan(Date.now());
  });

  it('getSession returns null for unknown id', () => {
    expect(getSession('does-not-exist')).toBeNull();
  });

  it('destroySession invalidates the session', async () => {
    const { sessionId } = await createSession();
    expect(getSession(sessionId)).not.toBeNull();
    destroySession(sessionId);
    expect(getSession(sessionId)).toBeNull();
  });

  it('validateCsrf matches session csrf', async () => {
    const { sessionId, csrf } = await createSession();
    const s = getSession(sessionId)!;
    expect(validateCsrf(s, csrf)).toBe(true);
    expect(validateCsrf(s, 'wrong-csrf')).toBe(false);
    expect(validateCsrf(null, csrf)).toBe(false);
  });

  it('getSession expires after explicit expiry', async () => {
    const { sessionId } = await createSession();
    expect(getSession(sessionId)).not.toBeNull();
    const db = new DatabaseSync(config.DB_PATH);
    const sidHash = crypto.createHash('sha256').update(sessionId).digest('hex');
    db.prepare('UPDATE sessions SET expires_at = ? WHERE sid_hash = ?')
      .run(Date.now() - 1000, sidHash);
    expect(getSession(sessionId)).toBeNull();
  });

  it('owner trusted sessions expire automatically when the owner password rotates', async () => {
    (config as any).IR_OWNER_PASSWORD = 'enabled';
    const currentHash = bcrypt.hashSync('test-admin-pass', 8);
    (config as any).WEB_PASSWORD = currentHash;

    const ok = await loginOwner('test-admin-pass');
    expect(ok).not.toBeNull();
    expect(getSession(ok!.sessionId)).not.toBeNull();

    (config as any).WEB_PASSWORD = bcrypt.hashSync('rotated-pass', 8);
    expect(getSession(ok!.sessionId)).toBeNull();

    const rotated = await loginOwner('rotated-pass');
    expect(rotated).not.toBeNull();
    expect(getSession(rotated!.sessionId)!.trusted).toBe(true);
  });
});
