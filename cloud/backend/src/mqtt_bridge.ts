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
  insertCommand,
  markCommandPublished,
} from './db';
import { bus } from './bus';

const SUB_SUFFIXES = ['telemetry', 'state', 'availability', 'commands/ack'];

let client: MqttClient | null = null;
let connected = false;

function stripPrefix(full: string): string {
  const pre = `${config.TOPIC_PREFIX}/${config.DEVICE_ID}/`;
  if (full.startsWith(pre)) return full.slice(pre.length);
  return full;
}

function handleMessage(suffix: string, json: string): void {
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
        firmware_version: String(d.firmware_version ?? ''),
        simulated,
      });
      upsertDeviceState({
        device_id: config.DEVICE_ID,
        availability: 'online',
        last_seen_at: now,
        data_freshness: 'fresh',
        updated_at: now,
        simulated,
      });
      const evt = { ...d, server_received_at: now };
      bus.emit('telemetry', evt);
      log.info('telemetry received', { seq: d.seq, temp: d.temperature_c, hum: d.humidity_pct });
    } else if (suffix === 'state') {
      const d = JSON.parse(json) as Record<string, any>;
      upsertDeviceState({
        device_id: config.DEVICE_ID,
        availability: 'online',
        last_seen_at: now,
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
      upsertDeviceState({
        device_id: config.DEVICE_ID,
        availability: status,
        last_seen_at: now,
        data_freshness: status === 'online' ? 'fresh' : 'stale',
        updated_at: now,
      });
      bus.emit('availability', d);
      if (status === 'offline') {
        insertEvent('availability_offline', config.DEVICE_ID, 'device reported offline (LWT)');
      } else if (status === 'online') {
        insertEvent('availability_online', config.DEVICE_ID, 'device reported online');
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

  client.on('message', (full: string, payload: Buffer) => {
    handleMessage(stripPrefix(full), payload.toString('utf-8'));
  });
}

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

// Helper: build + persist + publish a command. Returns the command record.
export function dispatchCommand(action: OutboundCommand['action'], opts: { power?: boolean; target_temperature_c?: number }): {
  command_id: string;
  status: string;
} {
  const command_id = uuid();
  const expires_at = Date.now() + 120_000;
  insertCommand({
    command_id,
    device_id: config.DEVICE_ID,
    action,
    requested_power: opts.power === undefined ? 0 : opts.power ? 1 : 0,
    requested_temperature_c: opts.target_temperature_c ?? 0,
    status: 'pending',
    created_at: Date.now(),
    expires_at,
  });
  const ok = publishCommand({ command_id, action, power: opts.power, target_temperature_c: opts.target_temperature_c, expires_at });
  return { command_id, status: ok ? 'pending' : 'failed_to_publish' };
}
