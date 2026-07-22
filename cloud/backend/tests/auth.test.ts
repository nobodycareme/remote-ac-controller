import { describe, it, expect, beforeEach } from 'vitest';
import crypto from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { verifyPassword, createSession, getSession, destroySession, validateCsrf } from '../src/auth';
import { initDb } from '../src/db';
import { config } from '../src/config';

// NOTE: setup.ts already points config.DB_PATH at a REAL temporary SQLite file
// (resolved through the `node:sqlite` alias -> real builtin). No mocks are used.
// Each test re-initializes the real schema so it runs against a real DB.
describe('auth', () => {
  beforeEach(async () => {
    // Real initDb against the temp DB_PATH from setup.ts (real node:sqlite).
    await initDb();
  });

  it('verifyPassword accepts correct bcrypt password', async () => {
    // verifyPassword is async (initializes/verifies the password hash) -> must await.
    expect(await verifyPassword('test-admin-pass')).toBe(true);
  });

  it('verifyPassword rejects wrong password', async () => {
    expect(await verifyPassword('nope')).toBe(false);
  });

  it('createSession (no role) defaults to an anonymous guest session', async () => {
    // createSession is async (awaits initPassword + writes the session row) -> must await.
    const { sessionId, csrf } = await createSession();
    const s = getSession(sessionId);
    expect(s).not.toBeNull();
    expect(s!.csrf).toBe(csrf);
    // §七 role model: an unauthenticated createSession() is a guest, NOT owner.
    expect(s!.user).toBe('guest');
    expect(s!.role).toBe('guest');
  });

  it('createSession("owner") mints an owner session bound to IR_OWNER_USER', async () => {
    const { sessionId, csrf } = await createSession('owner');
    const s = getSession(sessionId);
    expect(s).not.toBeNull();
    expect(s!.csrf).toBe(csrf);
    expect(s!.user).toBe('admin'); // IR_OWNER_USER default is 'admin'
    expect(s!.role).toBe('owner');
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

  it('getSession expires after TTL', async () => {
    const { sessionId } = await createSession();
    expect(getSession(sessionId)).not.toBeNull();
    // Backdate the PERSISTED session row's created_at beyond TTL (1h) in the REAL db.
    // (Mutating the in-memory object returned by getSession has no effect, since
    //  getSession re-reads created_at from the store.)
    const db = new DatabaseSync(config.DB_PATH);
    const sidHash = crypto.createHash('sha256').update(sessionId).digest('hex');
    db.prepare('UPDATE sessions SET created_at = ? WHERE sid_hash = ?')
      .run(Date.now() - (2 * 60 * 60 * 1000), sidHash);
    expect(getSession(sessionId)).toBeNull();
  });
});
