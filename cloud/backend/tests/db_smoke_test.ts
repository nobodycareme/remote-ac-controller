// Direct database smoke test using tsx
// CRITICAL: Set env vars BEFORE any imports (config.ts parses process.env at import time)
process.env.DB_PATH = '/tmp/_smoke_test.db';
process.env.WEB_PASSWORD = 'smoke-pass';
process.env.WEB_USER = 'admin';
process.env.SESSION_SECRET = 'smoke-secret';
process.env.DEVICE_ID = 'smoke-dev-01';
process.env.TOPIC_PREFIX = 'remote-ac/v1/devices';

import { initDb, insertTelemetry, upsertDeviceState, insertCommand, updateCommandAck, getLatestTelemetry, getDeviceState, getRecentCommands, getTelemetryHistory, insertEvent, getEvents, getDb } from '../src/db';
import fs from 'node:fs';

const results: string[] = [];
let pass = 0, fail = 0;

function check(name: string, fn: () => void) {
  try { fn(); results.push(name + ': PASS'); pass++; }
  catch(e: any) { results.push(name + ': FAIL - ' + e.message); fail++; }
}

// Clean up any old test DB
try { fs.unlinkSync('/tmp/_smoke_test.db'); fs.unlinkSync('/tmp/_smoke_test.db-wal'); fs.unlinkSync('/tmp/_smoke_test.db-shm'); } catch {}

// 1. Init DB
check('DATABASE_MIGRATION', () => {
  initDb();
  const db = getDb();
  const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").all() as any[];
  const names = tables.map((t: any) => t.name);
  ['schema_migrations','users','sessions','devices','telemetry','telemetry_minute','device_state','commands','events','weather_cache'].forEach(t => {
    if (!names.includes(t)) throw new Error('Missing table: ' + t);
  });
});

// 2. WAL mode check
check('DATABASE_WAL', () => {
  const db = getDb();
  const row = db.prepare('PRAGMA journal_mode').get() as any;
  if (row.journal_mode !== 'wal') throw new Error('WAL not enabled: ' + row.journal_mode);
});

// 3. Foreign key check
check('DATABASE_FOREIGN_KEYS', () => {
  const db = getDb();
  const row = db.prepare('PRAGMA foreign_keys').get() as any;
  if (row.foreign_keys !== 1) throw new Error('Foreign keys not enabled');
});

// 4. Insert 100 telemetry records
check('DATABASE_TELEMETRY_INSERT', () => {
  for (let i = 1; i <= 100; i++) {
    insertTelemetry({
      device_id: 'smoke-dev-01',
      seq: i,
      server_received_at: Date.now() - (100 - i) * 60000,
      temperature_c: 25 + i * 0.1,
      humidity_pct: 50 + i % 20,
      sensor_ok: 1,
      wifi_rssi_dbm: -50 - i % 30,
      free_heap_bytes: 30000 - i * 100,
      uptime_s: i * 60,
      wifi_reconnect_count: 0,
      mqtt_reconnect_count: 0,
      firmware_version: 'smoke-1.0',
      simulated: 1,
    });
  }
  const row = getLatestTelemetry();
  if (!row) throw new Error('No telemetry found');
  if (row.seq !== 100) throw new Error('Expected seq=100, got ' + row.seq);
});

// 5. History query
check('DATABASE_HISTORY_QUERY', () => {
  const history = getTelemetryHistory(3600000, 50);
  if (!history || history.length === 0) throw new Error('No history data');
  if (history.length > 50) throw new Error('Too many history points');
});

// 6. Upsert device state
check('DATABASE_DEVICE_STATE', () => {
  upsertDeviceState({
    device_id: 'smoke-dev-01',
    availability: 'online',
    last_seen_at: Date.now(),
    data_freshness: 'fresh',
    power_reported: 1,
    target_temperature_reported: 26,
    control_mode: 'cool',
    updated_at: Date.now(),
    simulated: 1,
  });
  const s = getDeviceState();
  if (!s) throw new Error('No device state');
  if (s.power_reported !== 1) throw new Error('power_reported wrong');
});

// 7. Command lifecycle
check('DATABASE_COMMAND_LIFECYCLE', () => {
  const cid = 'smoke-cmd-' + Date.now();
  insertCommand({
    command_id: cid,
    device_id: 'smoke-dev-01',
    action: 'set_state',
    requested_power: 1,
    requested_temperature_c: 25,
    status: 'pending',
    created_at: Date.now(),
    expires_at: Date.now() + 120000,
  });
  updateCommandAck(cid, 'accepted', Date.now(), 'ok');
  const cmds = getRecentCommands(10);
  const found = cmds.find((c: any) => c.command_id === cid);
  if (!found) throw new Error('Command not found after ack');
  if (found.status !== 'accepted') throw new Error('Status not updated');
});

// 8. Event insertion
check('DATABASE_EVENTS', () => {
  insertEvent('info', 'smoke-dev-01', 'Smoke test event');
  const events = getEvents(5);
  if (events.length === 0) throw new Error('No events found');
});

// 9. Transaction rollback
check('DATABASE_TRANSACTION_ROLLBACK', () => {
  const db = getDb();
  db.exec('CREATE TABLE IF NOT EXISTS smoke_rollback(id INTEGER PRIMARY KEY, val TEXT)');
  db.prepare('INSERT INTO smoke_rollback(val) VALUES(?)').run('persist');
  db.exec('BEGIN');
  db.prepare('INSERT INTO smoke_rollback(val) VALUES(?)').run('should-rollback');
  db.exec('ROLLBACK');
  const rows = db.prepare('SELECT * FROM smoke_rollback').all();
  if (rows.length !== 1) throw new Error('Rollback failed, got ' + rows.length + ' rows');
  db.exec('DROP TABLE smoke_rollback');
});

// 10. Constraint test (UNIQUE)
check('DATABASE_CONSTRAINT', () => {
  const db = getDb();
  db.exec('CREATE TABLE IF NOT EXISTS smoke_unique(id INTEGER PRIMARY KEY, code TEXT UNIQUE)');
  db.prepare('INSERT INTO smoke_unique(code) VALUES(?)').run('A');
  try {
    db.prepare('INSERT INTO smoke_unique(code) VALUES(?)').run('A');
    throw new Error('UNIQUE should have failed');
  } catch(e: any) {
    if (!e.message.includes('UNIQUE')) throw new Error('Wrong error: ' + e.message);
  }
  db.exec('DROP TABLE smoke_unique');
});

// 11. Reopen database
check('DATABASE_REOPEN', () => {
  const db = getDb();
  db.close();
  initDb();
  const row = getLatestTelemetry();
  if (!row || row.seq !== 100) throw new Error('Reopen data lost');
});

// Results
console.log('\n=== DATABASE SMOKE TEST RESULTS ===');
results.forEach(r => console.log(r));
console.log('PASS: ' + pass + '/' + (pass + fail) + ' FAIL: ' + fail);

// Cleanup
try { fs.unlinkSync('/tmp/_smoke_test.db'); fs.unlinkSync('/tmp/_smoke_test.db-wal'); fs.unlinkSync('/tmp/_smoke_test.db-shm'); } catch {}

if (fail > 0) { console.log('DATABASE_SMOKE_TEST_FAILED'); process.exit(1); }
console.log('DATABASE_SMOKE_TEST_ALL_PASS');
