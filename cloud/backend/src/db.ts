import { DatabaseSync } from 'node:sqlite';
import { config } from './config';
import { log } from './logger';

let db: DatabaseSync;

export interface TelemetryRow {
  device_id: string;
  seq: number;
  server_received_at: number;
  temperature_c: number;
  humidity_pct: number;
  sensor_ok: number;
  wifi_rssi_dbm: number;
  free_heap_bytes: number;
  uptime_s: number;
  wifi_reconnect_count: number;
  mqtt_reconnect_count: number;
  mqtt_initial_connect_count: number;
  mqtt_reconnect_attempt_count: number;
  mqtt_reconnect_success_count: number;
  firmware_version: string;
  simulated: number;
}

export function initDb(): void {
  // Clear cached prepared statements (they belong to old db instance)
  Object.keys(stmts).forEach(k => delete stmts[k]);
  db = new DatabaseSync(config.DB_PATH);
  db.exec('PRAGMA journal_mode = WAL');
  db.exec('PRAGMA foreign_keys = ON');
  db.exec('PRAGMA busy_timeout = 5000');
  db.exec(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY,
      applied_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
      sid_hash TEXT PRIMARY KEY,
      user_name TEXT NOT NULL DEFAULT 'admin',
      csrf TEXT NOT NULL DEFAULT '',
      created_at INTEGER NOT NULL,
      last_access INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS devices (
      device_id TEXT PRIMARY KEY,
      name TEXT,
      registered_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS telemetry (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      device_id TEXT NOT NULL,
      seq INTEGER,
      server_received_at INTEGER NOT NULL,
      temperature_c REAL,
      humidity_pct REAL,
      sensor_ok INTEGER,
      wifi_rssi_dbm INTEGER,
      free_heap_bytes INTEGER,
      uptime_s INTEGER,
      wifi_reconnect_count INTEGER,
      mqtt_reconnect_count INTEGER,
      firmware_version TEXT,
      simulated INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_telemetry_dev_time ON telemetry(device_id, server_received_at);

    CREATE TABLE IF NOT EXISTS telemetry_minute (
      minute_ts INTEGER NOT NULL,
      device_id TEXT NOT NULL,
      temperature_c_avg REAL,
      humidity_pct_avg REAL,
      sample_count INTEGER,
      PRIMARY KEY (minute_ts, device_id)
    );

    CREATE TABLE IF NOT EXISTS device_state (
      device_id TEXT PRIMARY KEY,
      availability TEXT,
      last_seen_at INTEGER,
      data_freshness TEXT,
      power_reported INTEGER,
      target_temperature_reported INTEGER,
      control_mode TEXT,
      updated_at INTEGER,
      simulated INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS commands (
      command_id TEXT PRIMARY KEY,
      device_id TEXT NOT NULL,
      action TEXT,
      requested_power INTEGER,
      requested_temperature_c INTEGER,
      status TEXT,
      created_at INTEGER,
      published_at INTEGER,
      acknowledged_at INTEGER,
      completed_at INTEGER,
      expires_at INTEGER,
      failure_reason TEXT,
      requested_by TEXT,
      idempotency_key TEXT UNIQUE
    );
    CREATE INDEX IF NOT EXISTS idx_commands_created ON commands(created_at);

    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_type TEXT,
      device_id TEXT,
      message TEXT,
      created_at INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);

    CREATE TABLE IF NOT EXISTS weather_cache (
      location TEXT PRIMARY KEY,
      payload_json TEXT,
      observed_at INTEGER,
      fetched_at INTEGER,
      expires_at INTEGER
    );
  `);
  // Migration: add idempotency_key column if missing.
  // NOTE: older SQLite builds reject `ALTER TABLE ADD COLUMN ... UNIQUE` inline, so we
  // add the column without the constraint, then create a separate UNIQUE index
  // (NULLs are not considered equal, so existing all-NULL rows are fine).
  try {
    db.exec('ALTER TABLE commands ADD COLUMN idempotency_key TEXT');
  } catch (e: any) {
    if (!/duplicate column/i.test(e?.message ?? '')) {
      log.warn('idempotency migration skip', { err: e?.message });
    }
  }
  try {
    db.exec('CREATE UNIQUE INDEX IF NOT EXISTS idx_commands_idempotency ON commands(idempotency_key)');
  } catch (e: any) {
    log.warn('idempotency index skip', { err: e?.message });
  }
  // Migration: add ir_code_id column for real-IR actions (Section 七/八/九).
  try {
    db.exec('ALTER TABLE commands ADD COLUMN ir_code_id TEXT');
  } catch (e: any) {
    if (!/duplicate column/i.test(e?.message ?? '')) {
      log.warn('ir_code_id migration skip', { err: e?.message });
    }
  }
  // Migration: add role column to sessions (Section 七 owner/guest model). The
  // sessions table is also declared in auth.ts; this migration keeps the schema
  // created by initDb in sync for existing deployments.
  try {
    db.exec("ALTER TABLE sessions ADD COLUMN role TEXT NOT NULL DEFAULT 'guest'");
  } catch (e: any) {
    if (!/duplicate column/i.test(e?.message ?? '')) {
      log.warn('sessions.role migration skip', { err: e?.message });
    }
  }

  // Migration: add liveness-split columns (Section 五). `availability` is reused as the
  // raw availability hint (online/offline/unknown). `last_seen_at` is advanced ONLY by real
  // activity (telemetry/state/ack); availability messages (retained or not) must NOT touch it.
  const livenessCols = [
    'availability_payload_sent_at INTEGER',
    'availability_received_at INTEGER',
    'availability_retained INTEGER DEFAULT 0',
    'last_telemetry_at INTEGER',
    'last_heartbeat_at INTEGER',
  ];
  for (const col of livenessCols) {
    const name = col.split(' ')[0];
    try {
      db.exec(`ALTER TABLE device_state ADD COLUMN ${col}`);
    } catch (e: any) {
      if (!/duplicate column/i.test(e?.message ?? '')) {
        log.warn('liveness migration skip', { col: name, err: e?.message });
      }
    }
  }

  // Migration: add MQTT reconnect-counter columns (Section 四) so the dashboard can
  // prove initial-connect vs runtime-reconnect instrumentation. Added to BOTH
  // device_state (current values) and telemetry (time-series history).
  const counterCols = [
    'mqtt_initial_connect_count INTEGER',
    'mqtt_reconnect_attempt_count INTEGER',
    'mqtt_reconnect_success_count INTEGER',
  ];
  for (const col of counterCols) {
    const name = col.split(' ')[0];
    try { db.exec(`ALTER TABLE device_state ADD COLUMN ${col}`); }
    catch (e: any) { if (!/duplicate column/i.test(e?.message ?? '')) log.warn('counter migration skip', { table: 'device_state', col: name, err: e?.message }); }
    try { db.exec(`ALTER TABLE telemetry ADD COLUMN ${col}`); }
    catch (e: any) { if (!/duplicate column/i.test(e?.message ?? '')) log.warn('counter migration skip', { table: 'telemetry', col: name, err: e?.message }); }
  }

  log.info('db initialized', { path: config.DB_PATH });
}

// Prepared statement cache
const stmts: Record<string, any> = {};
function prep(sql: string) {
  if (!stmts[sql]) stmts[sql] = db.prepare(sql);
  return stmts[sql];
}

export function insertTelemetry(r: TelemetryRow): void {
  prep(`INSERT INTO telemetry
    (device_id, seq, server_received_at, temperature_c, humidity_pct, sensor_ok, wifi_rssi_dbm, free_heap_bytes, uptime_s, wifi_reconnect_count, mqtt_reconnect_count, mqtt_initial_connect_count, mqtt_reconnect_attempt_count, mqtt_reconnect_success_count, firmware_version, simulated)
    VALUES (@device_id, @seq, @server_received_at, @temperature_c, @humidity_pct, @sensor_ok, @wifi_rssi_dbm, @free_heap_bytes, @uptime_s, @wifi_reconnect_count, @mqtt_reconnect_count, @mqtt_initial_connect_count, @mqtt_reconnect_attempt_count, @mqtt_reconnect_success_count, @firmware_version, @simulated)`).run(r);
}

export function upsertDeviceState(s: {
  device_id: string;
  availability?: string | null;
  last_seen_at?: number | null;
  data_freshness?: string | null;
  last_telemetry_at?: number | null;
  last_heartbeat_at?: number | null;
  availability_received_at?: number | null;
  availability_retained?: number | null;
  availability_payload_sent_at?: number | null;
  updated_at: number;
  simulated?: number | null;
  power_reported?: number | null;
  target_temperature_reported?: number | null;
  control_mode?: string | null;
  mqtt_initial_connect_count?: number | null;
  mqtt_reconnect_attempt_count?: number | null;
  mqtt_reconnect_success_count?: number | null;
}): void {
  // COALESCE keeps each existing column value when the caller passes null. This is the
  // core of the false-online fix: callers that pass `last_seen_at: null` (availability
  // messages) leave last_seen_at UNCHANGED, while telemetry/ack pass a real timestamp to
  // advance it. `availability` is only a hint and never proves realtime presence.
  prep(`INSERT INTO device_state
    (device_id, availability, last_seen_at, data_freshness, last_telemetry_at, last_heartbeat_at,
     availability_received_at, availability_retained, availability_payload_sent_at, updated_at, simulated, power_reported, target_temperature_reported, control_mode,
     mqtt_initial_connect_count, mqtt_reconnect_attempt_count, mqtt_reconnect_success_count)
    VALUES (@device_id, @availability, @last_seen_at, @data_freshness, @last_telemetry_at, @last_heartbeat_at,
      @availability_received_at, @availability_retained, @availability_payload_sent_at, @updated_at, @simulated, @power_reported, @target_temperature_reported, @control_mode,
      @mqtt_initial_connect_count, @mqtt_reconnect_attempt_count, @mqtt_reconnect_success_count)
    ON CONFLICT(device_id) DO UPDATE SET
      availability = COALESCE(excluded.availability, device_state.availability),
      last_seen_at = COALESCE(excluded.last_seen_at, device_state.last_seen_at),
      data_freshness = COALESCE(excluded.data_freshness, device_state.data_freshness),
      last_telemetry_at = COALESCE(excluded.last_telemetry_at, device_state.last_telemetry_at),
      last_heartbeat_at = COALESCE(excluded.last_heartbeat_at, device_state.last_heartbeat_at),
      availability_received_at = COALESCE(excluded.availability_received_at, device_state.availability_received_at),
      availability_retained = COALESCE(excluded.availability_retained, device_state.availability_retained),
      availability_payload_sent_at = COALESCE(excluded.availability_payload_sent_at, device_state.availability_payload_sent_at),
      updated_at = excluded.updated_at,
      simulated = COALESCE(excluded.simulated, device_state.simulated),
      power_reported = COALESCE(excluded.power_reported, device_state.power_reported),
      target_temperature_reported = COALESCE(excluded.target_temperature_reported, device_state.target_temperature_reported),
      control_mode = COALESCE(excluded.control_mode, device_state.control_mode),
      mqtt_initial_connect_count = COALESCE(excluded.mqtt_initial_connect_count, device_state.mqtt_initial_connect_count),
      mqtt_reconnect_attempt_count = COALESCE(excluded.mqtt_reconnect_attempt_count, device_state.mqtt_reconnect_attempt_count),
      mqtt_reconnect_success_count = COALESCE(excluded.mqtt_reconnect_success_count, device_state.mqtt_reconnect_success_count)
  `).run({
    device_id: s.device_id,
    availability: s.availability ?? null,
    last_seen_at: s.last_seen_at ?? null,
    data_freshness: s.data_freshness ?? null,
    last_telemetry_at: s.last_telemetry_at ?? null,
    last_heartbeat_at: s.last_heartbeat_at ?? null,
    availability_received_at: s.availability_received_at ?? null,
    availability_retained: s.availability_retained ?? null,
    availability_payload_sent_at: s.availability_payload_sent_at ?? null,
    updated_at: s.updated_at,
    simulated: s.simulated ?? 0,
    power_reported: s.power_reported ?? null,
    target_temperature_reported: s.target_temperature_reported ?? null,
    control_mode: s.control_mode ?? null,
    mqtt_initial_connect_count: s.mqtt_initial_connect_count ?? null,
    mqtt_reconnect_attempt_count: s.mqtt_reconnect_attempt_count ?? null,
    mqtt_reconnect_success_count: s.mqtt_reconnect_success_count ?? null,
  });
}

export function insertCommand(c: {
  command_id: string; device_id: string; action: string; requested_power: number; requested_temperature_c: number;
  status: string; created_at: number; expires_at: number; failure_reason?: string; idempotency_key?: string | null;
}): void {
  prep(`INSERT OR IGNORE INTO commands
    (command_id, device_id, action, requested_power, requested_temperature_c, status, created_at, expires_at, failure_reason, idempotency_key)
    VALUES (@command_id, @device_id, @action, @requested_power, @requested_temperature_c, @status, @created_at, @expires_at, @failure_reason, @idempotency_key)`).run({
    command_id: c.command_id,
    device_id: c.device_id,
    action: c.action,
    requested_power: c.requested_power,
    requested_temperature_c: c.requested_temperature_c,
    status: c.status,
    created_at: c.created_at,
    expires_at: c.expires_at,
    failure_reason: c.failure_reason ?? null,
    idempotency_key: c.idempotency_key ?? null,
  });
}

/**
 * Atomic idempotent command insert.
 * - If a row with the same idempotency_key already exists, the INSERT OR IGNORE is a no-op
 *   (changes === 0) and we return the existing command WITHOUT inserting a new one.
 * - The caller must publish the MQTT command ONLY when `inserted === true`. This guarantees
 *   that the same idempotency key can never produce more than one MQTT publish, even under
 *   concurrent requests (SQLite serializes the write; only the winning writer sees changes > 0).
 */
export function tryInsertCommand(c: {
  command_id: string; device_id: string; action: string; requested_power: number; requested_temperature_c: number;
  status: string; created_at: number; expires_at: number; idempotency_key?: string | null;
}): { inserted: boolean; existing?: any } {
  const r = prep(`INSERT OR IGNORE INTO commands
    (command_id, device_id, action, requested_power, requested_temperature_c, status, created_at, expires_at, idempotency_key)
    VALUES (@command_id, @device_id, @action, @requested_power, @requested_temperature_c, @status, @created_at, @expires_at, @idempotency_key)`).run({
    command_id: c.command_id,
    device_id: c.device_id,
    action: c.action,
    requested_power: c.requested_power,
    requested_temperature_c: c.requested_temperature_c,
    status: c.status,
    created_at: c.created_at,
    expires_at: c.expires_at,
    idempotency_key: c.idempotency_key ?? null,
  });
  if ((r as any).changes > 0) return { inserted: true };
  const existing = getCommandByIdempotencyKey(c.idempotency_key ?? '');
  return { inserted: false, existing };
}

export function getCommandByIdempotencyKey(idempotency_key: string): any | null {
  if (!idempotency_key) return null;
  return prep(`SELECT * FROM commands WHERE idempotency_key=?`).get(idempotency_key);
}

/**
 * Atomic idempotent IR-action insert. Same guarantee as tryInsertCommand: the same
 * idempotency_key can never produce more than one MQTT publish. `ir_code_id` identifies
 * which PROGMEM vendor frame the device should emit.
 */
export function tryInsertIrCommand(c: {
  command_id: string; device_id: string; action: string; ir_code_id: string;
  status: string; created_at: number; expires_at: number; requested_by?: string; idempotency_key?: string | null;
}): { inserted: boolean; existing?: any } {
  const r = prep(`INSERT OR IGNORE INTO commands
    (command_id, device_id, action, ir_code_id, status, created_at, expires_at, requested_by, idempotency_key)
    VALUES (@command_id, @device_id, @action, @ir_code_id, @status, @created_at, @expires_at, @requested_by, @idempotency_key)`).run({
    command_id: c.command_id,
    device_id: c.device_id,
    action: c.action,
    ir_code_id: c.ir_code_id,
    status: c.status,
    created_at: c.created_at,
    expires_at: c.expires_at,
    requested_by: c.requested_by ?? null,
    idempotency_key: c.idempotency_key ?? null,
  });
  if ((r as any).changes > 0) return { inserted: true };
  const existing = getCommandByIdempotencyKey(c.idempotency_key ?? '');
  return { inserted: false, existing };
}

export function markCommandPublished(command_id: string, published_at: number): void {
  prep(`UPDATE commands SET status='published', published_at=@published_at WHERE command_id=@command_id`).run({ command_id, published_at });
}

export function updateCommandAck(command_id: string, status: string, acknowledged_at: number, reason?: string): void {
  prep(`UPDATE commands SET status=@status, acknowledged_at=@acknowledged_at, failure_reason=@reason WHERE command_id=@command_id`).run({ command_id, status, acknowledged_at, reason: reason ?? null });
}

export function insertEvent(event_type: string, device_id: string, message: string): void {
  prep(`INSERT INTO events (event_type, device_id, message, created_at) VALUES (@event_type, @device_id, @message, @created_at)`).run({ event_type, device_id, message, created_at: Date.now() });
}

export function setWeatherCache(location: string, payload_json: string, observed_at: number, fetched_at: number, expires_at: number): void {
  prep(`INSERT INTO weather_cache (location, payload_json, observed_at, fetched_at, expires_at)
    VALUES (@location, @payload_json, @observed_at, @fetched_at, @expires_at)
    ON CONFLICT(location) DO UPDATE SET payload_json=excluded.payload_json, observed_at=excluded.observed_at, fetched_at=excluded.fetched_at, expires_at=excluded.expires_at`).run({ location, payload_json, observed_at, fetched_at, expires_at });
}

// Queries
export function getLatestTelemetry(): any {
  return prep(`SELECT * FROM telemetry WHERE device_id=? ORDER BY server_received_at DESC LIMIT 1`).get(config.DEVICE_ID);
}
export function getDeviceState(): any {
  return prep(`SELECT * FROM device_state WHERE device_id=?`).get(config.DEVICE_ID);
}
export function getRecentCommands(limit = 20): any[] {
  return prep(`SELECT * FROM commands WHERE device_id=? ORDER BY created_at DESC LIMIT ?`).all(config.DEVICE_ID, limit);
}
export function getCommand(command_id: string): any {
  return prep(`SELECT * FROM commands WHERE command_id=?`).get(command_id);
}
/** Find a pending command with matching params within timeWindowMs. Used for deduplication. */
export function findPendingCommand(device_id: string, action: string, requested_power: number, requested_temperature_c: number, timeWindowMs: number): any | null {
  const since = Date.now() - timeWindowMs;
  return prep(
    `SELECT * FROM commands
     WHERE device_id=? AND action=? AND requested_power=? AND requested_temperature_c=?
       AND status='pending' AND created_at>=?
     ORDER BY created_at DESC LIMIT 1`
  ).get(device_id, action, requested_power, requested_temperature_c, since);
}
export function getEvents(limit = 50): any[] {
  return prep(`SELECT * FROM events ORDER BY created_at DESC LIMIT ?`).all(limit);
}
export function getWeatherCache(location: string): any {
  return prep(`SELECT * FROM weather_cache WHERE location=?`).get(location);
}

export function getTelemetryHistory(rangeMs: number, maxPoints = 240): { t: number; temperature_c: number; humidity_pct: number }[] {
  const start = Date.now() - rangeMs;
  const rows = prep(`SELECT (server_received_at/60000)*60000 AS t,
      AVG(temperature_c) AS temperature_c, AVG(humidity_pct) AS humidity_pct
    FROM telemetry WHERE device_id=? AND server_received_at>=? GROUP BY t ORDER BY t ASC`)
    .all(config.DEVICE_ID, start) as { t: number; temperature_c: number; humidity_pct: number }[];
  if (rows.length <= maxPoints) return rows;
  const step = Math.ceil(rows.length / maxPoints);
  const out: { t: number; temperature_c: number; humidity_pct: number }[] = [];
  for (let i = 0; i < rows.length; i += step) out.push(rows[i]);
  return out;
}

export function retentionCleanup(): { deletedTelemetry: number; deletedEvents: number } {
  const now = Date.now();
  const telCut = now - 7 * 86400_000;
  const evCut = now - 180 * 86400_000;
  const d1 = prep(`DELETE FROM telemetry WHERE server_received_at < ?`).run(telCut);
  const d2 = prep(`DELETE FROM events WHERE created_at < ?`).run(evCut);
  prep(`DELETE FROM commands WHERE created_at < ?`).run(evCut);
  log.info('retention cleanup', { deletedTelemetry: d1.changes, deletedEvents: d2.changes });
  return { deletedTelemetry: d1.changes, deletedEvents: d2.changes };
}

export function getDb(): DatabaseSync {
  return db;
}
