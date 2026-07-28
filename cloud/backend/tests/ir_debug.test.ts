import { describe, it, expect, beforeEach } from 'vitest';
import Fastify from 'fastify';
import cookie from '@fastify/cookie';
import { initDb, getDb, getRecentCommands } from '../src/db';
import { config } from '../src/config';
import { registerIrDebugRoutes } from '../src/routes/ir_debug';

const VALID_ORIGIN = 'https://ac.example.com';

function futureIso(ms = 60_000): string {
  return new Date(Date.now() + ms).toISOString();
}

function irActionRowCount(): number {
  return getRecentCommands(200).filter((c: any) => c.action === 'ir_action').length;
}

async function buildApp() {
  const app = Fastify();
  await app.register(cookie);
  await registerIrDebugRoutes(app);
  return app;
}

beforeEach(() => {
  initDb();
  getDb().exec('DELETE FROM ir_debug_commands; DELETE FROM ir_debug_sessions; DELETE FROM commands; DELETE FROM telemetry; DELETE FROM device_state;');
  (config as any).WEB_REAL_IR_ENABLED = false;
  (config as any).REAL_IR_DEBUG_MODE = false;
  (config as any).REAL_IR_DEBUG_EXPIRES_AT = '';
  (config as any).REAL_IR_DEBUG_ALLOWED_CODE_ID = 'hisense_cool_24_quiet_swing_v_on_swing_h_on_power_on_v1';
  (config as any).REAL_IR_DEBUG_ALLOWED_CODE_LENGTH = 418;
  (config as any).REAL_IR_DEBUG_ALLOWED_CODE_SHA256 = 'e9ab43feca71acde248df5729d0cb0d228bdbcfb69f8513d43ea4b942cb6ac7e';
  (config as any).REAL_IR_DEBUG_MAX_TOTAL_COMMANDS = 0;
  (config as any).REAL_IR_DEBUG_COOLDOWN_SECONDS = 0;
  (config as any).REAL_IR_DEBUG_COMMAND_TTL_SECONDS = 30;
  (config as any).REAL_IR_DEBUG_SESSION_TTL_SECONDS = 3600;
  (config as any).PUBLIC_BASE_URL = VALID_ORIGIN;
});

describe('no-login real IR debug status', () => {
  it('defaults closed and does not mint an anonymous debug token', async () => {
    const app = await buildApp();
    const res = await app.inject({ method: 'GET', url: '/api/ir/debug/status' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.debugMode).toBe(false);
    expect(body.debugCsrf).toBeUndefined();
    expect(irActionRowCount()).toBe(0);
    await app.close();
  });

  it('supports a permanent unlimited debug window when expiry is blank and max commands is zero', async () => {
    const app = await buildApp();
    (config as any).REAL_IR_DEBUG_MODE = true;
    (config as any).REAL_IR_DEBUG_EXPIRES_AT = '';
    (config as any).REAL_IR_DEBUG_MAX_TOTAL_COMMANDS = 0;
    const res = await app.inject({ method: 'GET', url: '/api/ir/debug/status' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.debugWindowConfigured).toBe(true);
    expect(body.debugMode).toBe(true);
    expect(body.expiresAt).toBeNull();
    expect(body.expiresInSeconds).toBeNull();
    expect(body.remainingCommands).toBeNull();
    expect(body.maxCommands).toBeNull();
    expect(body.debugCsrf).toMatch(/[a-f0-9-]{36}/);
    expect(res.cookies.some((c: any) => c.name === 'ir_debug_sid')).toBe(true);
    await app.close();
  });

  it('mints a short anonymous debug session when explicitly enabled', async () => {
    const app = await buildApp();
    (config as any).REAL_IR_DEBUG_MODE = true;
    (config as any).REAL_IR_DEBUG_EXPIRES_AT = futureIso();
    const res = await app.inject({ method: 'GET', url: '/api/ir/debug/status' });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.debugMode).toBe(true);
    expect(body.debugCsrf).toMatch(/[a-f0-9-]{36}/);
    expect(res.cookies.some((c: any) => c.name === 'ir_debug_sid')).toBe(true);
    expect(irActionRowCount()).toBe(0);
    await app.close();
  });

  it('uses a recent same-code module ACK as a legacy metadata gate', async () => {
    const app = await buildApp();
    (config as any).REAL_IR_DEBUG_MODE = true;
    (config as any).REAL_IR_DEBUG_EXPIRES_AT = futureIso();
    const now = Date.now();
    getDb().prepare(`INSERT INTO commands
      (command_id, device_id, action, ir_code_id, status, created_at, acknowledged_at, expires_at, failure_reason, requested_by, idempotency_key)
      VALUES (?, ?, 'ir_action', ?, 'ir_executed', ?, ?, ?, 'ir_module_ack', 'owner', ?)`)
      .run(
        '33333333-3333-4333-8333-333333333333',
        config.DEVICE_ID,
        config.REAL_IR_DEBUG_ALLOWED_CODE_ID,
        now - 1000,
        now - 500,
        now + 30_000,
        'legacy-ack-idem',
      );
    const res = await app.inject({ method: 'GET', url: '/api/ir/debug/status' });
    const body = res.json();
    expect(body.telemetryMetadataUsable).toBe(false);
    expect(body.legacyModuleAckPass).toBe(true);
    expect(body.irGateSource).toBe('recent_module_ack_legacy');
    expect(body.irReady).toBe(true);
    expect(body.codeIdMatch).toBe(true);
    expect(body.codeLengthMatch).toBe(true);
    expect(body.codeShaMatch).toBe(true);
    await app.close();
  });
});

describe('no-login real IR debug transmit deny paths have zero side effects', () => {
  async function debugSession(app: Fastify.FastifyInstance) {
    (config as any).REAL_IR_DEBUG_MODE = true;
    (config as any).REAL_IR_DEBUG_EXPIRES_AT = futureIso();
    const res = await app.inject({ method: 'GET', url: '/api/ir/debug/status' });
    const sid = res.cookies.find((c: any) => c.name === 'ir_debug_sid')?.value;
    const csrf = res.json().debugCsrf;
    return { sid, csrf };
  }

  function body() {
    return JSON.stringify({
      confirm: true,
      commandId: '11111111-1111-4111-8111-111111111111',
      idempotencyKey: '22222222-2222-4222-8222-222222222222',
      raw: 'ignored',
      codeId: 'attacker_supplied_code',
    });
  }

  it('bad Origin is denied before session/command creation', async () => {
    const app = await buildApp();
    (config as any).REAL_IR_DEBUG_MODE = true;
    (config as any).REAL_IR_DEBUG_EXPIRES_AT = futureIso();
    const before = irActionRowCount();
    const res = await app.inject({
      method: 'POST',
      url: '/api/ir/debug/transmit',
      headers: { origin: 'https://evil.example.com', 'content-type': 'application/json' },
      payload: body(),
    });
    expect(res.statusCode).toBe(403);
    expect(res.json().errorCode).toBe('ORIGIN_DENIED');
    expect(irActionRowCount()).toBe(before);
    await app.close();
  });

  it('missing anonymous debug session is denied with no command row', async () => {
    const app = await buildApp();
    (config as any).REAL_IR_DEBUG_MODE = true;
    (config as any).REAL_IR_DEBUG_EXPIRES_AT = futureIso();
    const res = await app.inject({
      method: 'POST',
      url: '/api/ir/debug/transmit',
      headers: { origin: VALID_ORIGIN, 'content-type': 'application/json' },
      payload: body(),
    });
    expect(res.statusCode).toBe(403);
    expect(res.json().errorCode).toBe('DEBUG_SESSION_REQUIRED');
    expect(irActionRowCount()).toBe(0);
    await app.close();
  });

  it('valid anonymous session but WEB_REAL_IR_ENABLED=false is denied with no command row', async () => {
    const app = await buildApp();
    const { sid, csrf } = await debugSession(app);
    const res = await app.inject({
      method: 'POST',
      url: '/api/ir/debug/transmit',
      headers: { origin: VALID_ORIGIN, 'x-ir-debug-csrf': csrf, 'content-type': 'application/json' },
      cookies: { ir_debug_sid: sid },
      payload: body(),
    });
    const result = res.json();
    expect(res.statusCode).toBe(403);
    expect(result.errorCode).toBe('WEB_REAL_IR_DISABLED');
    expect(result.commandCreated).toBe(false);
    expect(result.mqttPublished).toBe(false);
    expect(result.deviceReceived).toBe(false);
    expect(result.uartFrameWritten).toBe(false);
    expect(irActionRowCount()).toBe(0);
    await app.close();
  });

  it('rejects any extra browser-supplied IR fields before creating a command', async () => {
    const app = await buildApp();
    (config as any).WEB_REAL_IR_ENABLED = true;
    const { sid, csrf } = await debugSession(app);
    const res = await app.inject({
      method: 'POST',
      url: '/api/ir/debug/transmit',
      headers: { origin: VALID_ORIGIN, 'x-ir-debug-csrf': csrf, 'content-type': 'application/json' },
      cookies: { ir_debug_sid: sid },
      payload: body(),
    });
    const result = res.json();
    expect(res.statusCode).toBe(400);
    expect(result.errorCode).toBe('INVALID_DEBUG_TRANSMIT_BODY');
    expect(result.commandCreated).toBe(false);
    expect(result.mqttPublished).toBe(false);
    expect(irActionRowCount()).toBe(0);
    await app.close();
  });
});
