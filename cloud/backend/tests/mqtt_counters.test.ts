import { describe, it, expect, beforeEach } from 'vitest';
import { initDb, getDb, getDeviceState } from '../src/db';
import { handleMessage } from '../src/mqtt_bridge';

// Section 四: regression test for the MQTT reconnect-counter instrumentation.
// The firmware now reports three counters (initial / reconnect-attempt / reconnect-success).
// This test verifies the backend parses and persists them, and that the INITIAL count
// is preserved across a runtime reconnect (only attempt/success advance).

const DEVICE = 'bedroom-ac-01';

function resetState(): void {
  const db = getDb();
  db.prepare('DELETE FROM device_state WHERE device_id=?').run(DEVICE);
  db.prepare(
    `INSERT INTO device_state (device_id, availability, last_seen_at, data_freshness, updated_at, simulated)
     VALUES (?, 'unknown', NULL, 'unknown', ?, 0)`
  ).run(DEVICE, Date.now());
}

function telemetryPayload(over: Record<string, any> = {}): string {
  return JSON.stringify({
    schema: 1,
    device_id: DEVICE,
    seq: 1,
    uptime_s: 100,
    temperature_c: 26,
    humidity_pct: 50,
    sensor_ok: true,
    wifi_rssi_dbm: -50,
    free_heap_bytes: 30000,
    wifi_reconnect_count: 0,
    mqtt_reconnect_count: 0,
    mqtt_initial_connect_count: 1,
    mqtt_reconnect_attempt_count: 0,
    mqtt_reconnect_success_count: 0,
    simulated: false,
    firmware_version: '0.4.0',
    ...over,
  });
}

describe('mqtt reconnect-counter parsing (Section 四)', () => {
  beforeEach(async () => {
    await initDb();
    resetState();
  });

  it('stores initial connect counters from the first telemetry', () => {
    handleMessage('telemetry', telemetryPayload());
    const st = getDeviceState();
    expect(st.mqtt_initial_connect_count).toBe(1);
    expect(st.mqtt_reconnect_attempt_count).toBe(0);
    expect(st.mqtt_reconnect_success_count).toBe(0);
  });

  it('preserves initial count and records reconnect after runtime recovery', () => {
    handleMessage('telemetry', telemetryPayload({
      seq: 2,
      mqtt_initial_connect_count: 1,
      mqtt_reconnect_attempt_count: 3,
      mqtt_reconnect_success_count: 2,
    }));
    const st = getDeviceState();
    // initial connect must stay 1 (it is the FIRST boot connect, not a reconnect)
    expect(st.mqtt_initial_connect_count).toBe(1);
    expect(st.mqtt_reconnect_attempt_count).toBe(3);
    expect(st.mqtt_reconnect_success_count).toBe(2);
  });
});
