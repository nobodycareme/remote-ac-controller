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
      sid TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL,
      created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL,
      FOREIGN KEY (user_id) REFERENCES users(id)
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
      requested_by TEXT
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
    (device_id, seq, server_received_at, temperature_c, humidity_pct, sensor_ok, wifi_rssi_dbm, free_heap_bytes, uptime_s, wifi_reconnect_count, mqtt_reconnect_count, firmware_version, simulated)
    VALUES (@device_id, @seq, @server_received_at, @temperature_c, @humidity_pct, @sensor_ok, @wifi_rssi_dbm, @free_heap_bytes, @uptime_s, @wifi_reconnect_count, @mqtt_reconnect_count, @firmware_version, @simulated)`).run(r);
}

export function upsertDeviceState(s: {
  device_id: string; availability?: string; last_seen_at: number; data_freshness: string;
  power_reported?: number; target_temperature_reported?: number; control_mode?: string; updated_at: number; simulated?: number;
}): void {
  prep(`INSERT INTO device_state
    (device_id, availability, last_seen_at, data_freshness, power_reported, target_temperature_reported, control_mode, updated_at, simulated)
    VALUES (@device_id, @availability, @last_seen_at, @data_freshness, @power_reported, @target_temperature_reported, @control_mode, @updated_at, @simulated)
    ON CONFLICT(device_id) DO UPDATE SET
      availability=excluded.availability, last_seen_at=excluded.last_seen_at, data_freshness=excluded.data_freshness,
      power_reported=excluded.power_reported, target_temperature_reported=excluded.target_temperature_reported,
      control_mode=excluded.control_mode, updated_at=excluded.updated_at, simulated=excluded.simulated`).run({
    device_id: s.device_id,
    availability: s.availability ?? null,
    last_seen_at: s.last_seen_at,
    data_freshness: s.data_freshness,
    power_reported: s.power_reported ?? null,
    target_temperature_reported: s.target_temperature_reported ?? null,
    control_mode: s.control_mode ?? null,
    updated_at: s.updated_at,
    simulated: s.simulated ?? 0,
  });
}

export function insertCommand(c: {
  command_id: string; device_id: string; action: string; requested_power: number; requested_temperature_c: number;
  status: string; created_at: number; expires_at: number; failure_reason?: string;
}): void {
  prep(`INSERT OR IGNORE INTO commands
    (command_id, device_id, action, requested_power, requested_temperature_c, status, created_at, expires_at, failure_reason)
    VALUES (@command_id, @device_id, @action, @requested_power, @requested_temperature_c, @status, @created_at, @expires_at, @failure_reason)`).run({
    command_id: c.command_id,
    device_id: c.device_id,
    action: c.action,
    requested_power: c.requested_power,
    requested_temperature_c: c.requested_temperature_c,
    status: c.status,
    created_at: c.created_at,
    expires_at: c.expires_at,
    failure_reason: c.failure_reason ?? null,
  });
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
