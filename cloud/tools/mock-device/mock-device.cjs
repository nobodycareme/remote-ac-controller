// mock-device.cjs — Simulates the ESP8266 AC controller for local closed-loop testing.
// It speaks the EXACT same MQTT topic + JSON contract as the firmware:
//   publishes: telemetry, availability (LWT online/offline)
//   subscribes: commands/set
//   publishes: commands/ack  (blocked_by_ir_policy — mirroring IR-disabled firmware)
// Run: node mock-device.cjs   (with NODE_PATH=../backend/node_modules)
'use strict';
const mqtt = require('mqtt');
const fs = require('fs');
const path = require('path');

const DEVICE_ID = process.env.DEVICE_ID || 'bedroom-ac-01';
const USERNAME = process.env.MOCK_USERNAME || process.env.MQTT_USERNAME || 'bedroom-ac-01';
const PASSWORD = process.env.MOCK_PASSWORD || process.env.MQTT_PASSWORD || 'mock-device-password';
const BROKER_URL = process.env.BROKER_URL || 'mqtt://localhost:1883';
const TOPIC_PREFIX = process.env.TOPIC_PREFIX || 'remote-ac/v1/devices';
const TELEMETRY_MS = parseInt(process.env.TELEMETRY_MS || '5000', 10);
const FIRMWARE_VERSION = process.env.MOCK_FW || 'mock-0.4.0-cloud-foundation';

const t = (suffix) => `${TOPIC_PREFIX}/${DEVICE_ID}/${suffix}`;

const opts = { clientId: DEVICE_ID, username: USERNAME, password: PASSWORD, clean: true, reconnectPeriod: 3000 };
if (BROKER_URL.startsWith('mqtts')) {
  const caPath = process.env.MQTT_CA_PATH || path.resolve(__dirname, '../../broker/certs/ca.crt');
  opts.ca = fs.readFileSync(caPath);
  opts.rejectUnauthorized = true;
}
const will = { topic: t('availability'), payload: JSON.stringify({ status: 'offline' }), qos: 0, retain: true };

const client = mqtt.connect(BROKER_URL, { ...opts, will });

let seq = 0;
let recentIds = [];
const MAX_RECENT = 32;

function publishAvailability(status) {
  client.publish(t('availability'), JSON.stringify({ status }), { qos: 0, retain: true });
}

function publishTelemetry() {
  seq++;
  // gentle sinusoidal variation around 27C / 50%
  const phase = seq / 12;
  const temp = +(27 + Math.sin(phase) * 1.5).toFixed(1);
  const hum = Math.round(50 + Math.cos(phase) * 4);
  const now = Date.now();
  const payload = {
    schema: 1,
    device_id: DEVICE_ID,
    seq,
    uptime_s: seq * (TELEMETRY_MS / 1000),
    temperature_c: temp,
    humidity_pct: hum,
    sensor_ok: true,
    wifi_rssi_dbm: -55,
    free_heap_bytes: 23400,
    wifi_reconnect_count: 0,
    mqtt_reconnect_count: 0,
    simulated: true,
    firmware_version: FIRMWARE_VERSION,
  };
  client.publish(t('telemetry'), JSON.stringify(payload), { qos: 0 });
  console.log(`[mock] telemetry #${seq} temp=${temp}C hum=${hum}%`);
}

// --- command validation (mirrors firmware command_service.cpp) ---
function jsonGetInt(json, key, def = 0) {
  const m = json.match(new RegExp('"' + key + '":\\s*(-?\\d+)'));
  return m ? parseInt(m[1], 10) : def;
}
function jsonGetStr(json, key, def = '') {
  const m = json.match(new RegExp('"' + key + '":\\s*"([^"]*)"'));
  return m ? m[1] : def;
}

client.on('connect', () => {
  console.log(`[mock] connected to ${BROKER_URL} as ${USERNAME}`);
  publishAvailability('online');
  client.subscribe(t('commands/set'), { qos: 1 }, (err) => {
    if (err) console.error('[mock] subscribe error', err.message);
    else console.log('[mock] subscribed commands/set');
  });
  publishTelemetry();
  setInterval(publishTelemetry, TELEMETRY_MS);
});

client.on('error', (e) => console.error('[mock] error', e.message));
client.on('close', () => console.log('[mock] disconnected'));

client.on('message', (topicFull, payload) => {
  const json = payload.toString('utf-8');
  console.log(`[mock] cmd <- ${json}`);
  const command_id = jsonGetStr(json, 'command_id');
  const action = jsonGetStr(json, 'action');
  const expires_at = jsonGetInt(json, 'expires_at');
  const target_temperature_c = jsonGetInt(json, 'target_temperature_c');
  const power = jsonGetInt(json, 'power', 0) !== 0;

  let status = 'rejected';
  let reason = 'invalid_schema';

  if (!command_id || !['set_state', 'set_power', 'set_temperature'].includes(action)) {
    status = 'rejected';
    reason = 'invalid_schema';
  } else if (expires_at && expires_at < Math.floor(Date.now() / 1000)) {
    status = 'expired';
    reason = 'expired';
  } else if (recentIds.includes(command_id)) {
    status = 'rejected';
    reason = 'duplicate';
  } else if ((action === 'set_state' || action === 'set_temperature') && (target_temperature_c < 16 || target_temperature_c > 30)) {
    status = 'rejected';
    reason = 'temperature_out_of_range';
  } else {
    // IR mutating commands are disabled (mirrors ENABLE_IR_MUTATING_COMMANDS=0)
    status = 'blocked_by_ir_policy';
    reason = 'real_ir_control_disabled';
  }

  if (status !== 'rejected' || reason === 'invalid_schema' || reason === 'expired' || reason === 'duplicate' || reason === 'temperature_out_of_range') {
    if (command_id && !recentIds.includes(command_id) && status !== 'rejected') {
      recentIds.push(command_id);
      if (recentIds.length > MAX_RECENT) recentIds.shift();
    }
  }

  const ack = JSON.stringify({
    schema: 1,
    command_id,
    status,
    reason,
    received_uptime_s: seq * (TELEMETRY_MS / 1000),
  });
  client.publish(t('commands/ack'), ack, { qos: 0 });
  console.log(`[mock] ack -> ${ack}`);
});

process.on('SIGINT', () => {
  publishAvailability('offline');
  setTimeout(() => process.exit(0), 200);
});
