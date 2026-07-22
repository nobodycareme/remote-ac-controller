// Task §二/§五/§八 — integration tests proving that every real-IR DENY path
// produces ZERO side effects: no ir_action command row is created, no MQTT publish
// happens, and REAL_IR_TRANSMIT_COUNT stays at 0. This is the regression guard for
// the spurious-guest-403 incident: a guest (or bad-CSRF / bad-origin / kill-switch-off
// caller) must be refused with a structured envelope and must NEVER cause an IR transmit.
import { describe, it, expect, beforeEach } from 'vitest';
import Fastify from 'fastify';
import cookie from '@fastify/cookie';
import { initDb, getRecentCommands } from '../src/db';
import { config } from '../src/config';
import { createSession } from '../src/auth';
import { registerAuthRoutes } from '../src/routes/auth';
import { registerAcRoutes } from '../src/routes/ac';

const IR_CODE = 'hisense_cool_24_quiet_swing_v_on_swing_h_on_power_on_v1';
const VALID_ORIGIN = (config.ALLOWED_ORIGINS || 'https://ac.example.com').split(',')[0].trim();

function irActionRowCount(): number {
  // REAL_IR_TRANSMIT_COUNT proxy: number of persisted ir_action command rows.
  return getRecentCommands(200).filter((c: any) => c.action === 'ir_action').length;
}

async function buildApp() {
  const app = Fastify();
  await app.register(cookie);
  await registerAuthRoutes(app);
  await registerAcRoutes(app);
  return app;
}

async function guestSession(app: Fastify.FastifyInstance) {
  const res = await app.inject({ method: 'GET', url: '/api/auth/session', headers: { origin: VALID_ORIGIN } });
  const sid = res.cookies.find((c: any) => c.name === 'sid')?.value;
  const csrf = res.json().csrf as string;
  return { sid: sid!, csrf };
}

const irBody = (idem: string) => JSON.stringify({ ir_code_id: IR_CODE, idempotency_key: idem });

beforeEach(async () => {
  await initDb();
  // Safe defaults: kill switch OFF, no owner password.
  (config as any).WEB_REAL_IR_ENABLED = false;
  (config as any).IR_OWNER_PASSWORD = '';
});

describe('Task §二/§五 — guest 403 has zero side effects', () => {
  it('guest POST /api/ac/ir-action → 403 OWNER_REQUIRED; no ir_action row; REAL_IR_TRANSMIT_COUNT=0', async () => {
    const app = await buildApp();
    const before = irActionRowCount();
    const { sid, csrf } = await guestSession(app);
    const res = await app.inject({
      method: 'POST',
      url: '/api/ac/ir-action',
      headers: { origin: VALID_ORIGIN, 'x-csrf-token': csrf, 'content-type': 'application/json' },
      cookies: { sid },
      payload: irBody('idem-guest-01'),
    });
    const body = res.json();
    expect(res.statusCode).toBe(403);
    expect(body.errorCode).toBe('OWNER_REQUIRED');
    // Structured envelope must assert NOTHING happened downstream.
    expect(body.commandCreated).toBe(false);
    expect(body.mqttPublished).toBe(false);
    expect(body.deviceReceived).toBe(false);
    expect(body.irTransmitted).toBe(false);
    expect(body.ir_control).toBe('disabled');
    // DB: no IR command row created; transmit count unchanged (and is zero).
    expect(irActionRowCount()).toBe(before);
    expect(irActionRowCount()).toBe(0);
    await app.close();
  });

  it('even with kill switch ON + owner password set, a GUEST is still denied (role gate first) and no row is created', async () => {
    const app = await buildApp();
    (config as any).WEB_REAL_IR_ENABLED = true;
    (config as any).IR_OWNER_PASSWORD = 'test-owner-pass';
    const before = irActionRowCount();
    const { sid, csrf } = await guestSession(app);
    const res = await app.inject({
      method: 'POST',
      url: '/api/ac/ir-action',
      headers: { origin: VALID_ORIGIN, 'x-csrf-token': csrf, 'content-type': 'application/json' },
      cookies: { sid },
      payload: irBody('idem-guest-02'),
    });
    expect(res.statusCode).toBe(403);
    expect(res.json().errorCode).toBe('OWNER_REQUIRED');
    expect(irActionRowCount()).toBe(before);
    expect(irActionRowCount()).toBe(0);
    await app.close();
  });
});

describe('Task §八 — structured deny envelope for all IR-deny paths', () => {
  it('owner + kill switch OFF → 403 REAL_IR_DISABLED; no row; irTransmitted=false', async () => {
    const app = await buildApp();
    const { sessionId, csrf } = await createSession('owner');
    const before = irActionRowCount();
    const res = await app.inject({
      method: 'POST',
      url: '/api/ac/ir-action',
      headers: { origin: VALID_ORIGIN, 'x-csrf-token': csrf, 'content-type': 'application/json' },
      cookies: { sid: sessionId },
      payload: irBody('idem-owner-off'),
    });
    const body = res.json();
    expect(res.statusCode).toBe(403);
    expect(body.errorCode).toBe('REAL_IR_DISABLED');
    expect(body.irTransmitted).toBe(false);
    expect(irActionRowCount()).toBe(before);
    expect(irActionRowCount()).toBe(0);
    await app.close();
  });

  it('owner + wrong CSRF → 403 CSRF_INVALID; no row', async () => {
    const app = await buildApp();
    const { sessionId } = await createSession('owner');
    const before = irActionRowCount();
    const res = await app.inject({
      method: 'POST',
      url: '/api/ac/ir-action',
      headers: { origin: VALID_ORIGIN, 'x-csrf-token': 'bad', 'content-type': 'application/json' },
      cookies: { sid: sessionId },
      payload: irBody('idem-owner-csrf'),
    });
    expect(res.statusCode).toBe(403);
    expect(res.json().errorCode).toBe('CSRF_INVALID');
    expect(irActionRowCount()).toBe(before);
    await app.close();
  });

  it('owner + bad origin → 403 ORIGIN_DENIED; no row', async () => {
    const app = await buildApp();
    const { sessionId, csrf } = await createSession('owner');
    const before = irActionRowCount();
    const res = await app.inject({
      method: 'POST',
      url: '/api/ac/ir-action',
      headers: { origin: 'https://evil.example.com', 'x-csrf-token': csrf, 'content-type': 'application/json' },
      cookies: { sid: sessionId },
      payload: irBody('idem-owner-origin'),
    });
    expect(res.statusCode).toBe(403);
    expect(res.json().errorCode).toBe('ORIGIN_DENIED');
    expect(irActionRowCount()).toBe(before);
    await app.close();
  });
});
