import { describe, it, expect, beforeEach } from 'vitest';
import { verifyPassword, createSession, getSession, destroySession, validateCsrf } from '../src/auth';

describe('auth', () => {
  it('verifyPassword accepts correct bcrypt password', () => {
    expect(verifyPassword('test-admin-pass')).toBe(true);
  });
  it('verifyPassword rejects wrong password', () => {
    expect(verifyPassword('nope')).toBe(false);
  });

  it('createSession / getSession round-trips and carries csrf', () => {
    const { sessionId, csrf } = createSession();
    const s = getSession(sessionId);
    expect(s).not.toBeNull();
    expect(s!.csrf).toBe(csrf);
    expect(s!.user).toBe('admin');
  });

  it('getSession returns null for unknown id', () => {
    expect(getSession('does-not-exist')).toBeNull();
  });

  it('destroySession invalidates the session', () => {
    const { sessionId } = createSession();
    expect(getSession(sessionId)).not.toBeNull();
    destroySession(sessionId);
    expect(getSession(sessionId)).toBeNull();
  });

  it('validateCsrf matches session csrf', () => {
    const { sessionId, csrf } = createSession();
    const s = getSession(sessionId)!;
    expect(validateCsrf(s, csrf)).toBe(true);
    expect(validateCsrf(s, 'wrong-csrf')).toBe(false);
    expect(validateCsrf(null, csrf)).toBe(false);
  });

  it('getSession expires after TTL', () => {
    const { sessionId } = createSession();
    const s = getSession(sessionId)!;
    // Simulate expiry by backdating createdAt beyond TTL (1h)
    s.createdAt = Date.now() - (2 * 60 * 60 * 1000);
    expect(getSession(sessionId)).toBeNull();
  });
});
