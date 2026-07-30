// MQTT bridge: subscribes to device topics, persists to SQLite, emits bus events,
// and publishes outbound control commands to commands/set.
import mqtt, { MqttClient } from 'mqtt';
import { v4 as uuid } from 'uuid';
import { config, topic } from './config';
import { log } from './logger';
import {
  insertTelemetry,
  upsertDeviceState,
  updateCommandAck,
  insertEvent,
  markCommandPublished,
  tryInsertCommand,
  tryInsertIrCommand,
  insertIrDebugCommand,
  getDeviceState,
} from './db';
import { evaluateDeviceLiveness } from './device_liveness';
import { bus } from './bus';

const SUB_SUFFIXES = ['telemetry', 'state', 'availability', 'commands/ack'];

let client: MqttClient | null = null;
let connected = false;

function stripPrefix(full: string): string {
  const pre = `${config.TOPIC_PREFIX}/${config.DEVICE_ID}/`;
  if (full.startsWith(pre)) return full.slice(pre.length);
  return full;
}

function handleMessage(suffix: string, json: string, retained = false): void {
  const now = Date.now();
  try {
    if (suffix === 'telemetry') {
      const d = JSON.parse(json) as Record<string, any>;
      const simulated = d.simulated === true ? 1 : 0;
      insertTelemetry({
        device_id: config.DEVICE_ID,
        seq: typeof d.seq === 'number' ? d.seq : 0,
        server_received_at: now,
        temperature_c: Number(d.temperature_c),
        humidity_pct: Number(d.humidity_pct),
        sensor_ok: d.sensor_ok === true || d.sensor_ok === 1 ? 1 : 0,
        wifi_rssi_dbm: Number(d.wifi_rssi_dbm),
        free_heap_bytes: Number(d.free_heap_bytes),
        uptime_s: Number(d.uptime_s),
        wifi_reconnect_count: Number(d.wifi_reconnect_count ?? 0),
        mqtt_reconnect_count: Number(d.mqtt_reconnect_count ?? 0),
        mqtt_initial_connect_count: Number(d.mqtt_initial_connect_count ?? 0),
        mqtt_reconnect_attempt_count: Number(d.mqtt_reconnect_attempt_count ?? 0),
        mqtt_reconnect_success_count: Number(d.mqtt_reconnect_success_count ?? 0),
        ir_ready: d.ir_ready === true || d.ir_ready === 1 ? 1 : 0,
        ir_code_id: typeof d.ir_code_id === 'string' ? d.ir_code_id : '',
        ir_code_length: Number(d.ir_code_length ?? 0),
        ir_code_sha256: typeof d.ir_code_sha256 === 'string' ? d.ir_code_sha256 : '',
        firmware_version: String(d.firmware_version ?? ''),
        simulated,
      });
      // REAL activity → advances last_seen_at AND last_telemetry_at.
      upsertDeviceState({
        device_id: config.DEVICE_ID,
        availability: 'online',
        last_seen_at: now,
        last_telemetry_at: now,
        data_freshness: 'fresh',
        updated_at: now,
        simulated,
        mqtt_initial_connect_count: Number(d.mqtt_initial_connect_count ?? 0),
        mqtt_reconnect_attempt_count: Number(d.mqtt_reconnect_attempt_count ?? 0),
        mqtt_reconnect_success_count: Number(d.mqtt_reconnect_success_count ?? 0),
      });
      const evt = { ...d, server_received_at: now };
      bus.emit('telemetry', evt);
      log.info('telemetry received', { seq: d.seq, temp: d.temperature_c, hum: d.humidity_pct });
    } else if (suffix === 'state') {
      const d = JSON.parse(json) as Record<string, any>;
      // state is also REAL activity → advances last_seen_at.
      upsertDeviceState({
        device_id: config.DEVICE_ID,
        availability: 'online',
        last_seen_at: now,
        last_telemetry_at: now,
        data_freshness: 'fresh',
        power_reported: typeof d.power === 'number' ? d.power : undefined,
        target_temperature_reported: typeof d.target_temperature_c === 'number' ? d.target_temperature_c : undefined,
        control_mode: typeof d.mode === 'string' ? d.mode : undefined,
        updated_at: now,
        simulated: d.simulated === true ? 1 : 0,
      });
      bus.emit('state', d);
    } else if (suffix === 'availability') {
      const d = JSON.parse(json) as Record<string, any>;
      const status = d.status === 'online' ? 'online' : d.status === 'offline' ? 'offline' : 'unknown';
      const payloadSentAt = typeof d.sent_at === 'number' ? d.sent_at : (typeof d.ts === 'number' ? d.ts : null);
      // CRITICAL (Section 五 false-online fix):
      // An availability message (retained online replayed at broker/backend restart, or
      // LWT offline) MUST NOT advance `last_seen_at`. We pass `last_seen_at: null` so the
      // COALESCE in upsertDeviceState PRESERVES the previous real-activity timestamp. The
      // trusted presence decision lives in evaluateDeviceLiveness(), driven by last_seen_at.
      const availabilityFields = {
        device_id: config.DEVICE_ID,
        availability: status,
        last_seen_at: null,
        last_telemetry_at: null,
        availability_received_at: now,
        availability_retained: retained ? 1 : 0,
        availability_payload_sent_at: payloadSentAt,
        updated_at: now,
      } as const;
      if (status === 'offline') {
        upsertDeviceState({ ...availabilityFields, data_freshness: 'stale' });
        bus.emit('availability', d);
        insertEvent('availability_offline', config.DEVICE_ID, 'device reported offline (LWT)');
      } else if (status === 'online') {
        // Do NOT refresh last_seen; until fresh telemetry arrives, freshness is 'unknown'.
        upsertDeviceState({ ...availabilityFields, data_freshness: 'unknown' });
        bus.emit('availability', d);
        insertEvent('availability_online', config.DEVICE_ID, 'device reported online');
      } else {
        upsertDeviceState({ ...availabilityFields, data_freshness: 'unknown' });
        bus.emit('availability', d);
      }
    } else if (suffix === 'commands/ack') {
      const d = JSON.parse(json) as Record<string, any>;
      const status = String(d.status ?? 'rejected');
      const reason = typeof d.reason === 'string' ? d.reason : undefined;
      updateCommandAck(String(d.command_id), status, now, reason);
      bus.emit('ack', d);
      bus.emit('command', { command_id: d.command_id, status, reason });
      log.info('ack received', { command_id: d.command_id, status, reason });
    }
  } catch (e: any) {
    log.error('mqtt message handler error', { suffix, err: e?.message });
  }
}

export function startMqttBridge(): void {
  client = mqtt.connect(config.MQTT_URL, {
    username: config.MQTT_USERNAME,
    password: config.MQTT_PASSWORD,
    clientId: 'remote-ac-backend',
    clean: true,
    reconnectPeriod: 3000,
    connectTimeout: 15000,
  });

  client.on('connect', () => {
    connected = true;
    log.info('mqtt bridge connected', { url: config.MQTT_URL });
    for (const s of SUB_SUFFIXES) {
      client!.subscribe(topic(s), { qos: 0 }, (err) => {
        if (err) log.error('subscribe failed', { topic: topic(s), err: err.message });
      });
    }
  });

  client.on('reconnect', () => {
    connected = false;
    log.warn('mqtt bridge reconnecting');
  });

  client.on('close', () => {
    connected = false;
  });

  client.on('error', (e: any) => {
    connected = false;
    log.error('mqtt bridge error', { err: e?.message });
  });

  client.on('message', (full: string, payload: Buffer, packet?: any) => {
    handleMessage(stripPrefix(full), payload.toString('utf-8'), !!(packet && packet.retain));
  });
}

// Exported for unit/regression tests (Section 五/六). Processes a single inbound
// device message the same way the live broker listener would.
export { handleMessage };

export function mqttConnected(): boolean {
  return connected;
}

export interface OutboundCommand {
  command_id: string;
  action: 'set_state' | 'set_power' | 'set_temperature';
  power?: boolean;
  target_temperature_c?: number;
  expires_at: number;
}

// Publish a control command to the device. Persists + marks published.
export function publishCommand(cmd: OutboundCommand): boolean {
  if (!client || !connected) {
    log.warn('publishCommand skipped: mqtt not connected');
    return false;
  }
  const payload = JSON.stringify({
    command_id: cmd.command_id,
    expires_at: cmd.expires_at,
    action: cmd.action,
    power: cmd.power === undefined ? undefined : cmd.power ? 1 : 0,
    target_temperature_c: cmd.target_temperature_c,
  });
  client.publish(topic('commands/set'), payload, { qos: 0 }, (err) => {
    if (err) {
      log.error('publish command failed', { command_id: cmd.command_id, err: err.message });
      return;
    }
    markCommandPublished(cmd.command_id, Date.now());
  });
  return true;
}

// Is the device currently online per the backend's trusted last-seen record?
// Single source of truth shared with the dashboard (evaluateDeviceLiveness).
export function isDeviceOnline(): boolean {
  return evaluateDeviceLiveness(getDeviceState()).online;
}

// ── Real-IR actions (Section 七/八/九) ──────────────────────────────────────
// These publish a vendor 22H-frame reference (ir_code_id) for the device to emit.
// Safety invariants:
//   - Production control and temporary debug control are separate switches.
//   - retain:false ALWAYS (no broker persistence / replay at reconnect).
//   - One-shot: identical idempotency_key → at most ONE publish (tryInsertIrCommand).
//   - Short TTL (IR_COMMAND_TTL_MS, ~25s) → stale commands rejected by firmware.
export function debugIrControlEnabled(): boolean {
  return !!config.WEB_REAL_IR_ENABLED;
}

export function productionIrControlEnabled(): boolean {
  return !!config.REAL_IR_PRODUCTION_CONTROL_ENABLED;
}

export interface OutboundIrCommand {
  command_id: string;
  ir_code_id: string; // PROGMEM code id the device emits (e.g. hisense_cool_24_quiet_swing_v_on_swing_h_on_power_on_v1)
  expires_at: number;
}

export function publishIrAction(cmd: OutboundIrCommand): boolean {
  if (!client || !connected) {
    log.warn('publishIrAction skipped: mqtt not connected');
    return false;
  }
  // NOTE: retain:false is mandatory — a retained IR command would be replayed by the
  // broker on every device reconnect, violating the "no replay after reconnect" rule.
  // QoS 1 (2026-07-28 集成轮): at-least-once delivery to the broker; duplicate delivery
  // at the device is absorbed by the firmware command_id exec-cache + expires_at TTL.
  const payload = JSON.stringify({
    command_id: cmd.command_id,
    type: 'ir_action',
    action: cmd.ir_code_id,
    expires_at: cmd.expires_at,
  });
  client.publish(topic('commands/set'), payload, { qos: 1, retain: false }, (err) => {
    if (err) {
      log.error('publish ir action failed', { command_id: cmd.command_id, ir_code_id: cmd.ir_code_id, err: err.message });
      return;
    }
    markCommandPublished(cmd.command_id, Date.now());
  });
  return true;
}

// Build + persist + publish a real-IR command. Mirrors dispatchCommand's idempotency
// contract but for ir_action. Returns the command record / denial reason.
export function dispatchIrAction(
  irCodeId: string,
  opts: {
    requested_by?: string;
    idempotency_key?: string;
    command_id?: string;
    ttl_ms?: number;
    control_mode?: 'production' | 'debug';
    debug?: {
      request_id: string;
      idempotency_key_hash: string;
      debug_session_hash: string;
      debug_window_key: string;
    };
  },
): {
  command_id: string;
  status: string;
  ir_code_id: string;
  idempotency_replay?: boolean;
  offline_rejected?: boolean;
  ir_disabled?: boolean;
  mqtt_published?: boolean;
} {
  const controlMode = opts.control_mode ?? 'production';
  const controlEnabled = controlMode === 'debug'
    ? debugIrControlEnabled()
    : productionIrControlEnabled();
  if (!controlEnabled) {
    log.warn('ir action refused: control disabled', { control_mode: controlMode, ir_code_id: irCodeId });
    return { command_id: '', status: 'ir_disabled', ir_code_id: irCodeId, ir_disabled: true };
  }
  if (!isDeviceOnline()) {
    log.warn('ir action refused: device offline', { ir_code_id: irCodeId });
    return { command_id: '', status: 'offline_rejected', ir_code_id: irCodeId, offline_rejected: true };
  }

  const command_id = opts.command_id ?? uuid();
  const ttlMs = Math.max(1, Math.min(opts.ttl_ms ?? config.IR_COMMAND_TTL_MS, 30_000));
  const createdAt = Date.now();
  const expires_at = createdAt + ttlMs;
  const res = tryInsertIrCommand({
    command_id,
    device_id: config.DEVICE_ID,
    action: 'ir_action',
    ir_code_id: irCodeId,
    status: 'pending',
    created_at: createdAt,
    expires_at,
    requested_by: opts.requested_by,
    idempotency_key: opts.idempotency_key ?? null,
  });

  if (!res.inserted) {
    const existing = res.existing;
    // Same key + different ir_code_id must NOT reuse the first command.
    const payloadMatches = !!existing && existing.ir_code_id === irCodeId;
    if (existing && !payloadMatches) {
      return { command_id: existing.command_id, status: 'idempotency_key_payload_mismatch', ir_code_id: irCodeId, idempotency_replay: true };
    }
    return { command_id: existing?.command_id ?? '', status: existing?.status ?? 'pending', ir_code_id: irCodeId, idempotency_replay: true };
  }

  if (opts.debug) {
    insertIrDebugCommand({
      request_id: opts.debug.request_id,
      command_id,
      idempotency_key_hash: opts.debug.idempotency_key_hash,
      debug_session_hash: opts.debug.debug_session_hash,
      debug_window_key: opts.debug.debug_window_key,
      created_at: createdAt,
      expires_at,
      code_id: irCodeId,
      status: 'pending',
    });
  }

  const ok = publishIrAction({ command_id, ir_code_id: irCodeId, expires_at });
  return { command_id, status: ok ? 'pending' : 'failed_to_publish', ir_code_id: irCodeId, idempotency_replay: false, mqtt_published: ok };
}

// Helper: build + persist + publish a command. Returns the command record.
// Strict idempotency: callers pass a client-generated Idempotency-Key. The same key always
// maps to the SAME command_id and produces AT MOST ONE MQTT publish:
//   - tryInsertCommand() does INSERT OR IGNORE keyed on the unique idempotency_key.
//   - Only the writer that actually inserted (changes > 0) publishes; a replay returns the
//     existing command_id without publishing again. Concurrent requests cannot bypass this
//     because SQLite serializes the write and the UNIQUE constraint guarantees a single winner.
// Offline gate: if the device is not online (by trusted last-seen), refuse to create/publish.
export function dispatchCommand(
  action: OutboundCommand['action'],
  opts: { power?: boolean; target_temperature_c?: number },
  idempotencyKey?: string,
): {
  command_id: string;
  status: string;
  idempotency_replay?: boolean;
  offline_rejected?: boolean;
  payload_mismatch?: boolean;
} {
  // Offline gate (backend-side, independent of any frontend disable).
  if (!isDeviceOnline()) {
    log.warn('command refused: device offline', { action });
    return { command_id: '', status: 'offline_rejected', offline_rejected: true };
  }

  const command_id = uuid();
  const expires_at = Date.now() + 120_000;
  const requested_power = opts.power === undefined ? 0 : opts.power ? 1 : 0;
  const requested_temperature_c = opts.target_temperature_c ?? 0;

  const res = tryInsertCommand({
    command_id,
    device_id: config.DEVICE_ID,
    action,
    requested_power,
    requested_temperature_c,
    status: 'pending',
    created_at: Date.now(),
    expires_at,
    idempotency_key: idempotencyKey ?? null,
  });

  if (!res.inserted) {
    // Another request with the same idempotency key already created this command.
    const existing = res.existing;
    // Strict payload binding: same key + DIFFERENT payload must NOT reuse the first
    // command (that would silently mask a real bug / fake success). Reject with 409.
    const payloadMatches =
      !!existing &&
      existing.action === action &&
      existing.requested_power === requested_power &&
      existing.requested_temperature_c === requested_temperature_c;
    if (existing && !payloadMatches) {
      log.warn('idempotency key reused with different payload — rejected', {
        idempotency_key: idempotencyKey,
        existing_action: existing?.action,
        action,
        existing_power: existing?.requested_power,
        requested_power,
        existing_temp: existing?.requested_temperature_c,
        requested_temp: requested_temperature_c,
      });
      return {
        command_id: existing.command_id,
        status: 'idempotency_key_payload_mismatch',
        idempotency_replay: true,
        payload_mismatch: true,
      };
    }
    log.info('command idempotent replay', {
      existing: existing?.command_id,
      action,
      idempotency_key: idempotencyKey,
    });
    return { command_id: existing?.command_id ?? '', status: existing?.status ?? 'pending', idempotency_replay: true };
  }

  // Fresh command — publish exactly once.
  const ok = publishCommand({ command_id, action, power: opts.power, target_temperature_c: opts.target_temperature_c, expires_at });
  return { command_id, status: ok ? 'pending' : 'failed_to_publish', idempotency_replay: false };
}
