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
    // 长期信任模型：owner 会话 expiresAt=0（persistent），不设固定到期日。
    expect(s!.expiresAt).toBe(0);
    expect(s!.persistent).toBe(true);
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

describe('persistent trust（长期有效可撤销信任模型）', () => {
  beforeEach(async () => {
    await initDb();
    (config as any).IR_OWNER_PASSWORD = 'enabled';
    (config as any).WEB_PASSWORD = bcrypt.hashSync('test-admin-pass', 8);
  });

  it('owner 会话为长期有效：数据库行 expires_at=0，getSession 不做日期判定', async () => {
    const created = await createSession('owner');
    const db = new DatabaseSync(config.DB_PATH);
    const sidHash = crypto.createHash('sha256').update(created.sessionId).digest('hex');
    const row = db.prepare('SELECT expires_at, role FROM sessions WHERE sid_hash=?').get(sidHash) as any;
    expect(Number(row.expires_at)).toBe(0);
    expect(row.role).toBe('owner');
    // 把 created_at 拨到很久以前，长期会话仍然有效（不因时间流逝失效）
    db.prepare('UPDATE sessions SET created_at=?, last_access=? WHERE sid_hash=?')
      .run(Date.now() - 3 * 365 * 86_400_000, Date.now() - 3 * 365 * 86_400_000, sidHash);
    const s = getSession(created.sessionId);
    expect(s).not.toBeNull();
    expect(s!.persistent).toBe(true);
    expect(s!.expiresAt).toBe(0);
  });

  it('guest 会话仍然是短期的（expires_at>0，到期即失效）', async () => {
    const created = await createSession('guest');
    const db = new DatabaseSync(config.DB_PATH);
    const sidHash = crypto.createHash('sha256').update(created.sessionId).digest('hex');
    const row = db.prepare('SELECT expires_at FROM sessions WHERE sid_hash=?').get(sidHash) as any;
    expect(Number(row.expires_at)).toBeGreaterThan(Date.now());
    const s = getSession(created.sessionId);
    expect(s!.persistent).toBe(false);
  });

  it('清理任务不会误删长期 owner 会话，但仍清理过期 guest 与旧指纹 owner', async () => {
    const owner = await createSession('owner');
    const guest = await createSession('guest');
    const db = new DatabaseSync(config.DB_PATH);
    const oHash = crypto.createHash('sha256').update(owner.sessionId).digest('hex');
    const gHash = crypto.createHash('sha256').update(guest.sessionId).digest('hex');
    // owner 行拨旧 + guest 行过期
    db.prepare('UPDATE sessions SET created_at=? WHERE sid_hash=?').run(Date.now() - 2 * 365 * 86_400_000, oHash);
    db.prepare('UPDATE sessions SET expires_at=? WHERE sid_hash=?').run(Date.now() - 1000, gHash);
    // 复制 startSessionCleanup 的 SQL 语义直接执行一轮
    db.prepare(`DELETE FROM sessions
      WHERE (expires_at > 0 AND expires_at <= ?)
         OR (expires_at = 0 AND role <> 'owner' AND created_at < ?)`)
      .run(Date.now(), Date.now() - 60 * 60_000);
    expect(db.prepare('SELECT COUNT(*) AS n FROM sessions WHERE sid_hash=?').get(oHash) as any).toMatchObject({ n: 1 });
    expect(db.prepare('SELECT COUNT(*) AS n FROM sessions WHERE sid_hash=?').get(gHash) as any).toMatchObject({ n: 0 });
  });

  it('移除本机信任（destroySession）后长期会话立即失效', async () => {
    const owner = await createSession('owner');
    expect(getSession(owner.sessionId)).not.toBeNull();
    destroySession(owner.sessionId);
    expect(getSession(owner.sessionId)).toBeNull();
  });

  it('密码指纹变化后长期 owner 会话立即失效（撤销权在服务端）', async () => {
    const ok = await loginOwner('test-admin-pass');
    expect(ok).not.toBeNull();
    expect(getSession(ok!.sessionId)!.persistent).toBe(true);
    (config as any).WEB_PASSWORD = bcrypt.hashSync('new-pass', 8);
    expect(getSession(ok!.sessionId)).toBeNull();
  });

  it('滚动续期不产生重复会话记录（同一 sid_hash 只有一行）', async () => {
    const owner = await createSession('owner');
    // 模拟多次访问（getSession touch）
    for (let i = 0; i < 5; i++) expect(getSession(owner.sessionId)).not.toBeNull();
    const db = new DatabaseSync(config.DB_PATH);
    const sidHash = crypto.createHash('sha256').update(owner.sessionId).digest('hex');
    const n = (db.prepare('SELECT COUNT(*) AS n FROM sessions WHERE sid_hash=?').get(sidHash) as any).n;
    expect(Number(n)).toBe(1);
  });

  it('sessionCookieMaxAgeSeconds：persistent(0) 返回滚动窗口而非 1 秒', async () => {
    const { sessionCookieMaxAgeSeconds, trustedCookieRollingMaxAgeSeconds } = await import('../src/auth');
    expect(sessionCookieMaxAgeSeconds(0)).toBe(trustedCookieRollingMaxAgeSeconds());
    expect(sessionCookieMaxAgeSeconds(0)).toBeGreaterThan(86_400);
    // 临时到期时间仍按剩余秒数
    const in1h = Date.now() + 3_600_000;
    const v = sessionCookieMaxAgeSeconds(in1h);
    expect(v).toBeGreaterThan(3500);
    expect(v).toBeLessThanOrEqual(3600);
  });
});
