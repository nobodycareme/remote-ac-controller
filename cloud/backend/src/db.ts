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
  ir_ready?: number;
  ir_code_id?: string;
  ir_code_length?: number;
  ir_code_sha256?: string;
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
      role TEXT NOT NULL DEFAULT 'guest',
      trusted_label TEXT NOT NULL DEFAULT '',
      owner_password_fingerprint TEXT NOT NULL DEFAULT '',
      csrf TEXT NOT NULL DEFAULT '',
      created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL DEFAULT 0,
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
      mqtt_initial_connect_count INTEGER,
      mqtt_reconnect_attempt_count INTEGER,
      mqtt_reconnect_success_count INTEGER,
      ir_ready INTEGER,
      ir_code_id TEXT,
      ir_code_length INTEGER,
      ir_code_sha256 TEXT,
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

    CREATE TABLE IF NOT EXISTS ir_debug_sessions (
      sid_hash TEXT PRIMARY KEY,
      csrf_hash TEXT NOT NULL,
      user_agent_hash TEXT,
      window_key TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL,
      last_access INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_ir_debug_sessions_expires ON ir_debug_sessions(expires_at);

    CREATE TABLE IF NOT EXISTS ir_debug_commands (
      request_id TEXT PRIMARY KEY,
      command_id TEXT UNIQUE,
      idempotency_key_hash TEXT UNIQUE NOT NULL,
      debug_session_hash TEXT NOT NULL,
      debug_window_key TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL,
      code_id TEXT NOT NULL,
      status TEXT NOT NULL,
      mqtt_published_at INTEGER,
      device_received_at INTEGER,
      code_validated_at INTEGER,
      uart_written_at INTEGER,
      module_ack_at INTEGER,
      terminal_at INTEGER,
      terminal_reason TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_ir_debug_commands_window ON ir_debug_commands(debug_window_key, created_at);
    CREATE INDEX IF NOT EXISTS idx_ir_debug_commands_command ON ir_debug_commands(command_id);

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

    -- ── AC 状态目录（2026-07-28 全量集成轮）─────────────────────────────
    -- 代码内 AC_STATES 目录在启动时同步进本表；enabled 为运行期独立启停开关
    -- （DB 值优先于代码默认值）。不存储任何帧字节。
    CREATE TABLE IF NOT EXISTS ac_states (
      state_id TEXT PRIMARY KEY,
      display_name TEXT NOT NULL,
      mode TEXT NOT NULL,
      temperature INTEGER NOT NULL DEFAULT 0,
      fan TEXT NOT NULL,
      swing_vertical INTEGER NOT NULL DEFAULT 0,
      swing_horizontal INTEGER NOT NULL DEFAULT 0,
      power_on INTEGER NOT NULL DEFAULT 0,
      frame_length INTEGER NOT NULL,
      frame_sha256 TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1,
      updated_at INTEGER NOT NULL
    );

    -- 定时任务：在指定 HH:MM（Asia/Shanghai 本地时）触发一个状态下发。
    -- days_mask 位0=周一 … 位6=周日；one_shot=1 时触发一次后自动禁用。
    CREATE TABLE IF NOT EXISTS ac_schedules (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL DEFAULT '',
      state_id TEXT NOT NULL,
      time_hhmm TEXT NOT NULL,
      days_mask INTEGER NOT NULL DEFAULT 127,
      one_shot INTEGER NOT NULL DEFAULT 0,
      enabled INTEGER NOT NULL DEFAULT 1,
      last_fired_minute TEXT NOT NULL DEFAULT '',
      last_fired_at INTEGER,
      created_by TEXT NOT NULL DEFAULT 'owner',
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_ac_schedules_enabled ON ac_schedules(enabled, time_hhmm);

    -- 温控自动化规则（双阈值滞回）。单行（id=1）为主规则。
    CREATE TABLE IF NOT EXISTS ac_temperature_rules (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      enabled INTEGER NOT NULL DEFAULT 0,
      on_threshold_c REAL NOT NULL DEFAULT 28.0,
      off_threshold_c REAL NOT NULL DEFAULT 26.0,
      on_state_id TEXT NOT NULL,
      off_state_id TEXT NOT NULL,
      min_interval_s INTEGER NOT NULL DEFAULT 600,
      sensor_stale_s INTEGER NOT NULL DEFAULT 180,
      manual_suppress_s INTEGER NOT NULL DEFAULT 1800,
      last_action TEXT NOT NULL DEFAULT '',
      last_action_at INTEGER,
      last_eval_reason TEXT NOT NULL DEFAULT '',
      last_eval_at INTEGER,
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    );

    -- 自动化执行审计（定时 + 温控 统一记录）。
    CREATE TABLE IF NOT EXISTS ac_automation_executions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source TEXT NOT NULL,            -- 'schedule' | 'temperature'
      rule_id INTEGER,
      state_id TEXT NOT NULL,
      command_id TEXT,
      status TEXT NOT NULL,            -- dispatched / skipped_* / failed_*
      detail TEXT NOT NULL DEFAULT '',
      created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_ac_auto_exec_created ON ac_automation_executions(created_at);
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
  const sessionCols = [
    "trusted_label TEXT NOT NULL DEFAULT ''",
    "owner_password_fingerprint TEXT NOT NULL DEFAULT ''",
    'expires_at INTEGER NOT NULL DEFAULT 0',
  ];
  for (const col of sessionCols) {
    const name = col.split(' ')[0];
    try {
      db.exec(`ALTER TABLE sessions ADD COLUMN ${col}`);
    } catch (e: any) {
      if (!/duplicate column/i.test(e?.message ?? '')) {
        log.warn('sessions migration skip', { col: name, err: e?.message });
      }
    }
  }
  try {
    db.exec('CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)');
    db.exec('CREATE INDEX IF NOT EXISTS idx_sessions_role ON sessions(role, owner_password_fingerprint)');
  } catch (e: any) {
    log.warn('sessions index skip', { err: e?.message });
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

  // Migration: redacted IR metadata from telemetry. The raw 418-byte frame stays
  // in firmware/private assets; backend stores only public code metadata.
  const telemetryIrCols = [
    'ir_ready INTEGER',
    'ir_code_id TEXT',
    'ir_code_length INTEGER',
    'ir_code_sha256 TEXT',
  ];
  for (const col of telemetryIrCols) {
    const name = col.split(' ')[0];
    try { db.exec(`ALTER TABLE telemetry ADD COLUMN ${col}`); }
    catch (e: any) { if (!/duplicate column/i.test(e?.message ?? '')) log.warn('telemetry ir migration skip', { col: name, err: e?.message }); }
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
    (device_id, seq, server_received_at, temperature_c, humidity_pct, sensor_ok, wifi_rssi_dbm, free_heap_bytes, uptime_s, wifi_reconnect_count, mqtt_reconnect_count, mqtt_initial_connect_count, mqtt_reconnect_attempt_count, mqtt_reconnect_success_count, ir_ready, ir_code_id, ir_code_length, ir_code_sha256, firmware_version, simulated)
    VALUES (@device_id, @seq, @server_received_at, @temperature_c, @humidity_pct, @sensor_ok, @wifi_rssi_dbm, @free_heap_bytes, @uptime_s, @wifi_reconnect_count, @mqtt_reconnect_count, @mqtt_initial_connect_count, @mqtt_reconnect_attempt_count, @mqtt_reconnect_success_count, @ir_ready, @ir_code_id, @ir_code_length, @ir_code_sha256, @firmware_version, @simulated)`).run({
    ...r,
    ir_ready: r.ir_ready ?? 0,
    ir_code_id: r.ir_code_id ?? '',
    ir_code_length: r.ir_code_length ?? 0,
    ir_code_sha256: r.ir_code_sha256 ?? '',
  });
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
  prep(`UPDATE ir_debug_commands SET status='published', mqtt_published_at=@published_at WHERE command_id=@command_id`).run({ command_id, published_at });
}

export function updateCommandAck(command_id: string, status: string, acknowledged_at: number, reason?: string): void {
  prep(`UPDATE commands SET status=@status, acknowledged_at=@acknowledged_at, failure_reason=@reason WHERE command_id=@command_id`).run({ command_id, status, acknowledged_at, reason: reason ?? null });
  const terminal = status === 'ir_executed' || status === 'ir_execute_failed' || status === 'ir_module_busy' || status === 'ir_unknown_code' || status === 'expired' || status === 'duplicate' || status === 'blocked_by_ir_policy';
  prep(`UPDATE ir_debug_commands SET
      status=@status,
      device_received_at=COALESCE(device_received_at, @acknowledged_at),
      code_validated_at=CASE WHEN @status='ir_executed' THEN COALESCE(code_validated_at, @acknowledged_at) ELSE code_validated_at END,
      uart_written_at=CASE WHEN @status='ir_executed' THEN COALESCE(uart_written_at, @acknowledged_at) ELSE uart_written_at END,
      module_ack_at=CASE WHEN @status='ir_executed' AND @reason='ir_module_ack' THEN COALESCE(module_ack_at, @acknowledged_at) ELSE module_ack_at END,
      terminal_at=CASE WHEN @terminal=1 THEN COALESCE(terminal_at, @acknowledged_at) ELSE terminal_at END,
      terminal_reason=CASE WHEN @terminal=1 THEN COALESCE(@reason, @status) ELSE terminal_reason END
    WHERE command_id=@command_id`).run({
      command_id,
      status,
      acknowledged_at,
      reason: reason ?? null,
      terminal: terminal ? 1 : 0,
    });
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

// ── AC 状态目录 / 定时 / 温控 / 自动化审计（2026-07-28 全量集成轮）────────────

/** 启动时将代码目录同步进 ac_states；保留 DB 中已有的 enabled 运行期开关值。 */
export function syncAcStates(states: Array<{
  stateId: string; displayName: string; mode: string; temperature: number; fan: string;
  swingVertical: boolean; swingHorizontal: boolean; powerOn: boolean;
  frameLength: number; frameSha256: string; enabled: boolean;
}>): void {
  const now = Date.now();
  for (const s of states) {
    prep(`INSERT INTO ac_states
      (state_id, display_name, mode, temperature, fan, swing_vertical, swing_horizontal, power_on, frame_length, frame_sha256, enabled, updated_at)
      VALUES (@state_id, @display_name, @mode, @temperature, @fan, @swing_vertical, @swing_horizontal, @power_on, @frame_length, @frame_sha256, @enabled, @updated_at)
      ON CONFLICT(state_id) DO UPDATE SET
        display_name = excluded.display_name,
        mode = excluded.mode,
        temperature = excluded.temperature,
        fan = excluded.fan,
        swing_vertical = excluded.swing_vertical,
        swing_horizontal = excluded.swing_horizontal,
        power_on = excluded.power_on,
        frame_length = excluded.frame_length,
        frame_sha256 = excluded.frame_sha256,
        -- enabled 保留 DB 现值（运行期开关不被代码默认值覆盖）
        updated_at = excluded.updated_at`).run({
      state_id: s.stateId,
      display_name: s.displayName,
      mode: s.mode,
      temperature: s.temperature,
      fan: s.fan,
      swing_vertical: s.swingVertical ? 1 : 0,
      swing_horizontal: s.swingHorizontal ? 1 : 0,
      power_on: s.powerOn ? 1 : 0,
      frame_length: s.frameLength,
      frame_sha256: s.frameSha256,
      enabled: s.enabled ? 1 : 0,
      updated_at: now,
    });
  }
}

export function getAcStateRows(): any[] {
  return prep(`SELECT * FROM ac_states ORDER BY
    CASE mode WHEN 'cool' THEN 0 WHEN 'dry' THEN 1 WHEN 'heat' THEN 2 WHEN 'off' THEN 3 ELSE 4 END,
    temperature, fan`).all();
}

export function getAcStateRow(stateId: string): any | null {
  return prep(`SELECT * FROM ac_states WHERE state_id=?`).get(stateId);
}

export function setAcStateEnabled(stateId: string, enabled: boolean): boolean {
  const r = prep(`UPDATE ac_states SET enabled=?, updated_at=? WHERE state_id=?`)
    .run(enabled ? 1 : 0, Date.now(), stateId);
  return Number((r as any).changes ?? 0) > 0;
}

// —— 定时任务 CRUD ——
export function insertAcSchedule(s: {
  name: string; state_id: string; time_hhmm: string; days_mask: number;
  one_shot: number; enabled: number; created_by: string;
}): number {
  const now = Date.now();
  const r = prep(`INSERT INTO ac_schedules
    (name, state_id, time_hhmm, days_mask, one_shot, enabled, created_by, created_at, updated_at)
    VALUES (@name, @state_id, @time_hhmm, @days_mask, @one_shot, @enabled, @created_by, @created_at, @updated_at)`)
    .run({ ...s, created_at: now, updated_at: now });
  return Number((r as any).lastInsertRowid ?? 0);
}

export function updateAcSchedule(id: number, patch: Partial<{
  name: string; state_id: string; time_hhmm: string; days_mask: number; one_shot: number; enabled: number;
}>): boolean {
  const existing = prep(`SELECT * FROM ac_schedules WHERE id=?`).get(id) as any;
  if (!existing) return false;
  const merged = { ...existing, ...patch, updated_at: Date.now() };
  prep(`UPDATE ac_schedules SET name=@name, state_id=@state_id, time_hhmm=@time_hhmm,
    days_mask=@days_mask, one_shot=@one_shot, enabled=@enabled, updated_at=@updated_at WHERE id=@id`).run(merged);
  return true;
}

export function deleteAcSchedule(id: number): boolean {
  const r = prep(`DELETE FROM ac_schedules WHERE id=?`).run(id);
  return Number((r as any).changes ?? 0) > 0;
}

export function listAcSchedules(): any[] {
  return prep(`SELECT * FROM ac_schedules ORDER BY time_hhmm, id`).all();
}

export function getAcSchedule(id: number): any | null {
  return prep(`SELECT * FROM ac_schedules WHERE id=?`).get(id);
}

export function listEnabledAcSchedules(): any[] {
  return prep(`SELECT * FROM ac_schedules WHERE enabled=1`).all();
}

/** 触发记账：同一分钟只允许触发一次（幂等锚点）。one_shot 触发后自动禁用。 */
export function markAcScheduleFired(id: number, minuteKey: string, oneShot: boolean): void {
  prep(`UPDATE ac_schedules SET last_fired_minute=?, last_fired_at=?, enabled=CASE WHEN ?=1 THEN 0 ELSE enabled END, updated_at=? WHERE id=?`)
    .run(minuteKey, Date.now(), oneShot ? 1 : 0, Date.now(), id);
}

// —— 温控规则（单主规则 id 自动） ——
export function getTemperatureRule(): any | null {
  return prep(`SELECT * FROM ac_temperature_rules ORDER BY id LIMIT 1`).get();
}

export function upsertTemperatureRule(patch: {
  enabled?: number; on_threshold_c?: number; off_threshold_c?: number;
  on_state_id?: string; off_state_id?: string; min_interval_s?: number;
  sensor_stale_s?: number; manual_suppress_s?: number;
}, defaults: { on_state_id: string; off_state_id: string }): any {
  const now = Date.now();
  const existing = getTemperatureRule();
  if (!existing) {
    prep(`INSERT INTO ac_temperature_rules
      (enabled, on_threshold_c, off_threshold_c, on_state_id, off_state_id, min_interval_s, sensor_stale_s, manual_suppress_s, created_at, updated_at)
      VALUES (@enabled, @on_threshold_c, @off_threshold_c, @on_state_id, @off_state_id, @min_interval_s, @sensor_stale_s, @manual_suppress_s, @created_at, @updated_at)`).run({
      enabled: patch.enabled ?? 0,
      on_threshold_c: patch.on_threshold_c ?? 28.0,
      off_threshold_c: patch.off_threshold_c ?? 26.0,
      on_state_id: patch.on_state_id ?? defaults.on_state_id,
      off_state_id: patch.off_state_id ?? defaults.off_state_id,
      min_interval_s: patch.min_interval_s ?? 600,
      sensor_stale_s: patch.sensor_stale_s ?? 180,
      manual_suppress_s: patch.manual_suppress_s ?? 1800,
      created_at: now,
      updated_at: now,
    });
    return getTemperatureRule();
  }
  const merged = { ...existing, ...patch, updated_at: now };
  prep(`UPDATE ac_temperature_rules SET enabled=@enabled, on_threshold_c=@on_threshold_c,
    off_threshold_c=@off_threshold_c, on_state_id=@on_state_id, off_state_id=@off_state_id,
    min_interval_s=@min_interval_s, sensor_stale_s=@sensor_stale_s, manual_suppress_s=@manual_suppress_s,
    updated_at=@updated_at WHERE id=@id`).run(merged);
  return getTemperatureRule();
}

export function recordTemperatureRuleAction(id: number, action: 'on' | 'off', reason: string): void {
  prep(`UPDATE ac_temperature_rules SET last_action=?, last_action_at=?, last_eval_reason=?, last_eval_at=?, updated_at=? WHERE id=?`)
    .run(action, Date.now(), reason, Date.now(), Date.now(), id);
}

export function recordTemperatureRuleEval(id: number, reason: string): void {
  prep(`UPDATE ac_temperature_rules SET last_eval_reason=?, last_eval_at=? WHERE id=?`)
    .run(reason, Date.now(), id);
}

// —— 自动化执行审计 ——
export function insertAutomationExecution(e: {
  source: 'schedule' | 'temperature'; rule_id: number | null; state_id: string;
  command_id?: string | null; status: string; detail?: string;
}): void {
  prep(`INSERT INTO ac_automation_executions (source, rule_id, state_id, command_id, status, detail, created_at)
    VALUES (@source, @rule_id, @state_id, @command_id, @status, @detail, @created_at)`).run({
    source: e.source,
    rule_id: e.rule_id ?? null,
    state_id: e.state_id,
    command_id: e.command_id ?? null,
    status: e.status,
    detail: e.detail ?? '',
    created_at: Date.now(),
  });
}

export function listAutomationExecutions(limit = 50): any[] {
  return prep(`SELECT * FROM ac_automation_executions ORDER BY created_at DESC LIMIT ?`).all(limit);
}

/** 温控 3 样本中位数：取最近 N 条真实(非模拟且 sensor_ok=1)遥测。 */
export function getRecentTelemetrySamples(limit = 3): Array<{ temperature_c: number; server_received_at: number }> {
  return prep(`SELECT temperature_c, server_received_at FROM telemetry
    WHERE device_id=? AND sensor_ok=1 AND simulated=0 AND temperature_c IS NOT NULL
    ORDER BY server_received_at DESC LIMIT ?`).all(config.DEVICE_ID, limit) as any[];
}

/** 手动抑制窗口：最近一次「人为发起」的 ir_action 时间（requested_by 非自动化）。 */
export function getLastManualIrCommandAt(): number | null {
  const row = prep(`SELECT created_at FROM commands
    WHERE device_id=? AND action='ir_action'
      AND (requested_by IS NULL OR requested_by NOT LIKE 'automation:%')
    ORDER BY created_at DESC LIMIT 1`).get(config.DEVICE_ID) as any;
  return row ? Number(row.created_at) : null;
}

export function upsertIrDebugSession(s: {
  sid_hash: string;
  csrf_hash: string;
  user_agent_hash: string;
  window_key: string;
  created_at: number;
  expires_at: number;
  last_access: number;
}): void {
  prep(`INSERT OR REPLACE INTO ir_debug_sessions
    (sid_hash, csrf_hash, user_agent_hash, window_key, created_at, expires_at, last_access)
    VALUES (@sid_hash, @csrf_hash, @user_agent_hash, @window_key, @created_at, @expires_at, @last_access)`).run(s);
}

export function getIrDebugSession(sid_hash: string): any | null {
  return prep(`SELECT * FROM ir_debug_sessions WHERE sid_hash=?`).get(sid_hash);
}

export function touchIrDebugSession(sid_hash: string, last_access: number): void {
  prep(`UPDATE ir_debug_sessions SET last_access=? WHERE sid_hash=?`).run(last_access, sid_hash);
}

export function deleteExpiredIrDebugSessions(now: number): void {
  prep(`DELETE FROM ir_debug_sessions WHERE expires_at <= ?`).run(now);
}

export function invalidateIrDebugSessions(): void {
  prep(`DELETE FROM ir_debug_sessions`).run();
}

export function insertIrDebugCommand(c: {
  request_id: string;
  command_id: string;
  idempotency_key_hash: string;
  debug_session_hash: string;
  debug_window_key: string;
  created_at: number;
  expires_at: number;
  code_id: string;
  status: string;
}): void {
  prep(`INSERT INTO ir_debug_commands
    (request_id, command_id, idempotency_key_hash, debug_session_hash, debug_window_key, created_at, expires_at, code_id, status)
    VALUES (@request_id, @command_id, @idempotency_key_hash, @debug_session_hash, @debug_window_key, @created_at, @expires_at, @code_id, @status)`).run(c);
}

export function getIrDebugCommandByIdempotencyHash(hash: string): any | null {
  return prep(`SELECT * FROM ir_debug_commands WHERE idempotency_key_hash=?`).get(hash);
}

export function countIrDebugWindowCommands(windowKey: string): number {
  const row = prep(`SELECT COUNT(*) AS n FROM ir_debug_commands WHERE debug_window_key=?`).get(windowKey) as any;
  return Number(row?.n ?? 0);
}

export function getLatestIrDebugWindowCommand(windowKey: string): any | null {
  return prep(`SELECT * FROM ir_debug_commands WHERE debug_window_key=? ORDER BY created_at DESC LIMIT 1`).get(windowKey);
}

export function getIrDebugCommandByCommandId(commandId: string): any | null {
  return prep(`SELECT * FROM ir_debug_commands WHERE command_id=?`).get(commandId);
}

export function countActiveIrCommands(now = Date.now()): number {
  const row = prep(`SELECT COUNT(*) AS n FROM commands
    WHERE device_id=? AND action='ir_action' AND expires_at > ?
      AND status IN ('pending','published')`).get(config.DEVICE_ID, now) as any;
  return Number(row?.n ?? 0);
}

export function expireStaleIrDebugCommands(now = Date.now()): number {
  const r = prep(`UPDATE ir_debug_commands
    SET status='expired', terminal_at=@now, terminal_reason='ttl_expired'
    WHERE expires_at <= @now AND terminal_at IS NULL AND status IN ('pending','published')`).run({ now });
  prep(`UPDATE commands
    SET status='expired', completed_at=@now, failure_reason='ttl_expired'
    WHERE device_id=@device_id AND action='ir_action' AND expires_at <= @now AND status IN ('pending','published')`).run({ now, device_id: config.DEVICE_ID });
  return Number((r as any).changes ?? 0);
}
