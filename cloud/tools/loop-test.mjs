// loop-test.mjs — Local closed-loop verification (no real ESP / no cloud server).
// Starts: aedes broker -> backend (tsx) -> mock device, then exercises the
//   web -> cloud -> device -> ACK path and asserts the mock gates.
//
// Usage:  node tools/loop-test.mjs
// Requires: backend/node_modules installed (aedes, mqtt, tsx, fastify, ...).
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import process from 'node:process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const BACKEND = resolve(ROOT, 'backend');
const NODE_MODULES = resolve(BACKEND, 'node_modules');
const DATA = resolve(ROOT, 'data');

const PORT = 3109;
const BASE = `http://127.0.0.1:${PORT}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const children = [];
function run(name, cmd, args, env, cwd) {
  const p = spawn(cmd, args, {
    env: { ...process.env, NODE_PATH: NODE_MODULES, ...env },
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  p.stdout.on('data', (d) => process.stdout.write(`[${name}] ${d}`));
  p.stderr.on('data', (d) => process.stderr.write(`[${name}/err] ${d}`));
  p.on('exit', (code) => console.log(`[${name}] exited ${code}`));
  children.push(p);
  return p;
}

function shutdown() {
  for (const c of children) {
    try {
      c.kill('SIGKILL');
    } catch {
      /* ignore */
    }
  }
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

const gates = {};
function assert(name, cond, detail = '') {
  gates[name] = cond;
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
}

async function main() {
  // 1) Broker (aedes) on 1883
  run('broker', process.execPath, [resolve(__dirname, 'broker-dev.cjs')], { BROKER_TCP_PORT: '1883' }, __dirname);
  await sleep(1500);

  // 2) Backend (tsx) pointing at local broker
  run(
    'backend',
    process.execPath,
    [resolve(NODE_MODULES, 'tsx/dist/cli.mjs'), 'src/index.ts'],
    {
      PORT: String(PORT),
      HOST: '127.0.0.1',
      MQTT_URL: 'mqtt://127.0.0.1:1883',
      MQTT_USERNAME: 'remote-ac-backend',
      MQTT_PASSWORD: 'mock-backend-pass',
      DEVICE_ID: 'bedroom-ac-01',
      TOPIC_PREFIX: 'remote-ac/v1/devices',
      WEB_USER: 'admin',
      WEB_PASSWORD: 'admin',
      SESSION_SECRET: 'test-secret',
      SESSION_TTL_MIN: '60',
      DB_PATH: resolve(DATA, 'loop_test.db'),
      ALLOWED_ORIGINS: `http://127.0.0.1:${PORT}`,
      WEATHER_CITY: '西安市',
      WEATHER_LATITUDE: '34.3416',
      WEATHER_LONGITUDE: '108.9398',
    },
    BACKEND
  );

  // 3) Mock device
  run(
    'mock',
    process.execPath,
    [resolve(__dirname, 'mock-device', 'mock-device.cjs')],
    {
      BROKER_URL: 'mqtt://127.0.0.1:1883',
      MOCK_USERNAME: 'bedroom-ac-01',
      MOCK_PASSWORD: 'mock-device-pass',
      DEVICE_ID: 'bedroom-ac-01',
      TOPIC_PREFIX: 'remote-ac/v1/devices',
      TELEMETRY_MS: '2000',
    },
    __dirname
  );

  // Wait for telemetry + backend to be ready
  await sleep(5000);

  const waitServer = async () => {
    for (let i = 0; i < 30; i++) {
      try {
        const r = await fetch(`${BASE}/api/auth/session`);
        if (r.ok) return true;
      } catch {
        /* retry */
      }
      await sleep(500);
    }
    return false;
  };
  assert('BACKEND_HTTP_UP', await waitServer());

  // Login
  let csrf = null;
  {
    const r = await fetch(`${BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'admin' }),
    });
    const j = await r.json();
    csrf = j.csrf;
    assert('WEB_LOGIN_OK', r.ok && !!csrf, `csrf=${!!csrf}`);
  }

  // Dashboard — telemetry should be present (mock device published)
  await sleep(3000);
  // Re-login capturing cookie
  const loginRes = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: 'admin' }),
  });
  const setCookie = loginRes.headers.get('set-cookie');
  const cookie = setCookie ? setCookie.split(';')[0] : '';
  csrf = (await loginRes.json()).csrf;

  const authHeaders = { cookie, 'x-csrf-token': csrf };
  let dash = null;
  {
    const r = await fetch(`${BASE}/api/dashboard`, { headers: authHeaders });
    dash = await r.json();
    const tel = dash.latest_telemetry;
    assert('MOCK_TELEMETRY_RECEIVED', !!tel && typeof tel.temperature_c === 'number', tel ? `temp=${tel.temperature_c}C hum=${tel.humidity_pct}%` : 'no telemetry');
    assert('MOCK_AVAILABILITY_ONLINE', dash.availability === 'online', `availability=${dash.availability}`);
  }

  // Send a command (set_state) -> device should ACK blocked_by_ir_policy
  let cmdId = null;
  {
    const r = await fetch(`${BASE}/api/ac/command`, {
      method: 'POST',
      headers: { ...authHeaders, 'content-type': 'application/json' },
      body: JSON.stringify({ action: 'set_state', power: true, target_temperature_c: 26 }),
    });
    const j = await r.json();
    console.log(`[debug] command resp http=${r.status} body=${JSON.stringify(j)}`);
    cmdId = j.command_id;
    assert('COMMAND_DISPATCHED', r.ok && !!cmdId, `command_id=${cmdId}`);
  }

  // Poll for ACK
  let ackSeen = false;
  let ackStatus = null;
  for (let i = 0; i < 20; i++) {
    await sleep(500);
    const r = await fetch(`${BASE}/api/dashboard`, { headers: authHeaders });
    const d = await r.json();
    const cmd = d.recent_commands?.find((c) => c.command_id === cmdId);
    if (cmd && cmd.status && cmd.status !== 'pending' && cmd.status !== 'failed_to_publish') {
      ackSeen = true;
      ackStatus = cmd.status;
      break;
    }
  }
  assert('DEVICE_ACK_RECEIVED', ackSeen, `status=${ackStatus}`);
  assert('IR_POLICY_BLOCKED', ackStatus === 'blocked_by_ir_policy', 'expected blocked_by_ir_policy (real IR disabled)');

  // Negative: out-of-range temperature must be rejected by backend schema
  {
    const r = await fetch(`${BASE}/api/ac/command`, {
      method: 'POST',
      headers: { ...authHeaders, 'content-type': 'application/json' },
      body: JSON.stringify({ action: 'set_temperature', target_temperature_c: 99 }),
    });
    assert('BACKEND_REJECTS_BAD_TEMP', r.status === 400, `http=${r.status}`);
  }

  // Negative: command without CSRF must be rejected
  {
    const r = await fetch(`${BASE}/api/ac/command`, {
      method: 'POST',
      headers: { cookie, 'content-type': 'application/json' },
      body: JSON.stringify({ action: 'set_power', power: true }),
    });
    assert('CSRF_REQUIRED', r.status === 403, `http=${r.status}`);
  }

  const allPass = Object.values(gates).every(Boolean);
  console.log('\n=== MOCK CLOSED-LOOP GATES ===');
  console.log(allPass ? 'MOCK_ALL_GATES_PASS=True' : 'MOCK_ALL_GATES_PASS=False');
  console.log(`commands/ack status observed: ${ackStatus}`);
  shutdown();
}

main().catch((e) => {
  console.error('loop-test error', e);
  shutdown();
});
