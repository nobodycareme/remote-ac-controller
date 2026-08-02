import { describe, it, expect, beforeEach } from 'vitest';
import Fastify from 'fastify';
import cookie from '@fastify/cookie';
import { initDb } from '../src/db';
import { config } from '../src/config';
import { createSession, getSession, loginOwner } from '../src/auth';
import { dispatchIrAction, productionIrControlEnabled } from '../src/mqtt_bridge';
import { requireOrigin, requireOwnerCsrf } from '../src/guards';

const IR_CODE = 'hisense_cool_24_quiet_swing_v_on_swing_h_on_power_on_v1';
const VALID_ORIGIN = config.ALLOWED_ORIGINS.split(',')[0].trim();

beforeEach(async () => {
  await initDb();
  (config as any).REAL_IR_PRODUCTION_CONTROL_ENABLED = false;
  (config as any).WEB_REAL_IR_ENABLED = false;
});

describe('production real IR control', () => {
  it('default production control is off', () => {
    expect(config.REAL_IR_PRODUCTION_CONTROL_ENABLED).toBe(false);
    expect(productionIrControlEnabled()).toBe(false);
  });

  it('dispatchIrAction refused when production control is off', () => {
    const res = dispatchIrAction(IR_CODE, {});
    expect(res.ir_disabled).toBe(true);
    expect(res.status).toBe('ir_disabled');
    expect(res.command_id).toBe('');
  });

  it('dispatchIrAction refused (offline) when production control is on but device offline', () => {
    (config as any).REAL_IR_PRODUCTION_CONTROL_ENABLED = true;
    const res = dispatchIrAction(IR_CODE, {});
    expect(res.offline_rejected).toBe(true);
    expect(res.status).toBe('offline_rejected');
  });
});

describe('owner / guest session model', () => {
  it('createSession() defaults to guest role', async () => {
    const { sessionId } = await createSession();
    const s = getSession(sessionId);
    expect(s).not.toBeNull();
    expect(s!.role).toBe('guest');
    expect(s!.trusted).toBe(false);
  });

  it("createSession('owner') carries owner role and trusted flag", async () => {
    const { sessionId } = await createSession('owner');
    const s = getSession(sessionId);
    expect(s!.role).toBe('owner');
    expect(s!.trusted).toBe(true);
  });

  it('loginOwner returns null when WEB_PASSWORD is not configured', async () => {
    const original = (config as any).WEB_PASSWORD;
    (config as any).WEB_PASSWORD = '';
    const r = await loginOwner('anything');
    (config as any).WEB_PASSWORD = original;
    expect(r).toBeNull();
  });

  it('loginOwner returns trusted owner session with correct password', async () => {
    const ok = await loginOwner('test-admin-pass');
    expect(ok).not.toBeNull();
    expect(ok!.user).toBe(config.WEB_USER);
    expect(ok!.trusted).toBe(true);
    const s = getSession(ok!.sessionId);
    expect(s!.role).toBe('owner');
    expect(s!.trusted).toBe(true);
  });

  it('loginOwner rejects wrong password', async () => {
    const r = await loginOwner('wrong-pass');
    expect(r).toBeNull();
  });
});

describe('requireOwnerCsrf guard denies non-owner / bad origin / bad csrf', () => {
  async function buildApp() {
    const app = Fastify();
    await app.register(cookie);
    app.get('/probe', { preHandler: [requireOrigin, requireOwnerCsrf] }, (_req, reply) => {
      reply.send({ ok: true, role: (getSession((_req as any).cookies?.sid) as any)?.role });
    });
    return app;
  }

  it('unauthenticated (no cookie) → 401', async () => {
    const app = await buildApp();
    const res = await app.inject({ method: 'GET', url: '/probe', headers: { origin: VALID_ORIGIN } });
    expect(res.statusCode).toBe(401);
    await app.close();
  });

  it('guest session → 403 owner_required', async () => {
    const app = await buildApp();
    const { sessionId, csrf } = await createSession();
    const res = await app.inject({
      method: 'GET',
      url: '/probe',
      headers: { origin: VALID_ORIGIN, 'x-csrf-token': csrf },
      cookies: { sid: sessionId },
    });
    expect(res.statusCode).toBe(403);
    expect(res.json().errorCode).toBe('OWNER_REQUIRED');
    await app.close();
  });

  it('owner session + valid origin + valid csrf → 200', async () => {
    const app = await buildApp();
    const { sessionId, csrf } = await createSession('owner');
    const res = await app.inject({
      method: 'GET',
      url: '/probe',
      headers: { origin: VALID_ORIGIN, 'x-csrf-token': csrf },
      cookies: { sid: sessionId },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().role).toBe('owner');
    await app.close();
  });

  it('owner session + invalid origin → 403 origin_denied', async () => {
    const app = await buildApp();
    const { sessionId, csrf } = await createSession('owner');
    const res = await app.inject({
      method: 'GET',
      url: '/probe',
      headers: { origin: 'https://evil.example.com', 'x-csrf-token': csrf },
      cookies: { sid: sessionId },
    });
    expect(res.statusCode).toBe(403);
    expect(res.json().errorCode).toBe('ORIGIN_DENIED');
    await app.close();
  });

  it('owner session + wrong csrf → 403 csrf_invalid', async () => {
    const app = await buildApp();
    const { sessionId } = await createSession('owner');
    const res = await app.inject({
      method: 'GET',
      url: '/probe',
      headers: { origin: VALID_ORIGIN, 'x-csrf-token': 'wrong-csrf' },
      cookies: { sid: sessionId },
    });
    expect(res.statusCode).toBe(403);
    expect(res.json().errorCode).toBe('CSRF_INVALID');
    await app.close();
  });
});
