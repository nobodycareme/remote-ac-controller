// Regression tests for the Section 五/六 false-online fix.
//
// The bug: backend treated a retained MQTT `availability=online` (replayed by the
// broker on every subscribe / backend restart) as proof of realtime presence and
// refreshed `last_seen_at`, so an offline/dead device was shown online forever and
// the command interface accepted commands it could never receive.
//
// These tests prove:
//   1. retained availability=online does NOT refresh last_seen_at and does NOT fake presence
//   2. retained availability=offline marks device offline immediately (LWT authoritative)
//   3. fresh telemetry advances last_seen_at and yields trusted online + fresh
//   4. backend restart replay of retained online does not report online (last_seen stale)
//   5. device recovers to online after telemetry arrives post-offline
import { describe, it, expect, beforeAll } from 'vitest';
// Aliased via vitest.config.ts so vite never transforms the `node:sqlite` builtin;
// a single shared db module instance is preserved across test files.
import { initDb, getDeviceState, upsertDeviceState, getDb } from '../src/db';
import { handleMessage } from '../src/mqtt_bridge';
import { evaluateDeviceLiveness } from '../src/device_liveness';

beforeAll(() => {
  initDb();
});

const DEVICE = 'bedroom-ac-01';

// Deterministic baseline: DELETE the row first, then INSERT with explicit values.
// NOTE: upsertDeviceState uses COALESCE so a subsequent `null` PRESERVES the prior
// value — passing null there would NOT clear a leaked field. A hard delete gives
// each test a clean, independent starting state.
function resetState(over: Record<string, any> = {}): void {
  getDb().prepare('DELETE FROM device_state WHERE device_id=?').run(DEVICE);
  upsertDeviceState({
    device_id: DEVICE,
    availability: 'unknown',
    last_seen_at: null,
    last_telemetry_at: null,
    data_freshness: 'unknown',
    updated_at: Date.now(),
    ...over,
  });
}

const TELEMETRY = (seq: number, mqttReconnect = 0) =>
  JSON.stringify({
    seq,
    temperature_c: 26,
    humidity_pct: 50,
    sensor_ok: 1,
    wifi_rssi_dbm: -50,
    free_heap_bytes: 23000,
    uptime_s: 10,
    firmware_version: 'v1',
    mqtt_reconnect_count: mqttReconnect,
  });

describe('Section 五/六 device liveness (false-online fix)', () => {
  it('T1: retained availability=online does NOT refresh last_seen_at and does not fake presence', () => {
    resetState();
    // Broker replays the retained online message on subscribe (retained=true).
    handleMessage('availability', JSON.stringify({ status: 'online' }), true);
    const s = getDeviceState();
    expect(s.availability).toBe('online');
    expect(s.availability_retained).toBe(1);
    // CRITICAL: last_seen_at must remain untouched (null here).
    expect(s.last_seen_at).toBeNull();
    const liv = evaluateDeviceLiveness(s);
    expect(liv.online).toBe(false); // not falsely online
    expect(liv.reason).toBe('last_seen_stale');
  });

  it('T2: retained availability=offline marks device offline immediately (LWT authoritative)', () => {
    resetState({ availability: 'online', last_seen_at: Date.now(), data_freshness: 'fresh' });
    handleMessage('availability', JSON.stringify({ status: 'offline' }), true);
    const s = getDeviceState();
    expect(s.availability).toBe('offline');
    const liv = evaluateDeviceLiveness(s);
    expect(liv.online).toBe(false);
    expect(liv.reason).toBe('availability_offline_lwt');
  });

  it('T3: fresh telemetry advances last_seen_at and yields trusted online + fresh', () => {
    // Start from the post-restart retained-online state (no real activity yet).
    resetState({ availability: 'online', last_seen_at: null, data_freshness: 'unknown' });
    handleMessage('availability', JSON.stringify({ status: 'online' }), true);
    expect(evaluateDeviceLiveness(getDeviceState()).online).toBe(false); // pre-telemetry
    handleMessage('telemetry', TELEMETRY(1));
    const s = getDeviceState();
    expect(s.last_seen_at).not.toBeNull();
    expect(s.last_telemetry_at).not.toBeNull();
    const liv = evaluateDeviceLiveness(s);
    expect(liv.online).toBe(true);
    expect(liv.data_freshness).toBe('fresh');
  });

  it('T4: backend restart replay of retained online does not report online (last_seen stale)', () => {
    // Simulate a row carried over from a previous run: retained online + last_seen 10 min ago.
    const old = Date.now() - 10 * 60 * 1000;
    resetState({ availability: 'online', last_seen_at: old, last_telemetry_at: old, data_freshness: 'stale', updated_at: old });
    // Broker replays retained availability=online on the new subscription.
    handleMessage('availability', JSON.stringify({ status: 'online' }), true);
    const s = getDeviceState();
    // last_seen must NOT have been bumped by the retained availability message.
    expect(s.last_seen_at).toBe(old);
    const liv = evaluateDeviceLiveness(s);
    expect(liv.online).toBe(false); // stale last_seen => offline
  });

  it('T5: device recovers to online after telemetry arrives post-offline', () => {
    const ago = Date.now() - 5 * 60 * 1000;
    resetState({ availability: 'offline', last_seen_at: ago, last_telemetry_at: ago, data_freshness: 'stale', updated_at: ago });
    expect(evaluateDeviceLiveness(getDeviceState()).online).toBe(false);
    // Device reconnects: non-retained online on connect, then real telemetry.
    handleMessage('availability', JSON.stringify({ status: 'online' }), false);
    handleMessage('telemetry', TELEMETRY(2, 1));
    const liv = evaluateDeviceLiveness(getDeviceState());
    expect(liv.online).toBe(true);
    expect(liv.data_freshness).toBe('fresh');
  });
});
