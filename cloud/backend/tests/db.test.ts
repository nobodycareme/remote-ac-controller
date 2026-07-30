import { describe, it, expect, beforeAll } from 'vitest';
import { initDb, insertTelemetry, upsertDeviceState, insertCommand, updateCommandAck, getLatestTelemetry, getDeviceState, getRecentCommands } from '../src/db';

beforeAll(() => {
  initDb();
});

describe('db telemetry + commands', () => {
  it('inserts telemetry and reads latest', () => {
    insertTelemetry({
      device_id: 'bedroom-ac-01',
      seq: 1,
      server_received_at: Date.now(),
      temperature_c: 27.5,
      humidity_pct: 54,
      sensor_ok: 1,
      wifi_rssi_dbm: -55,
      free_heap_bytes: 23400,
      uptime_s: 100,
      wifi_reconnect_count: 0,
      mqtt_reconnect_count: 0,
      firmware_version: 'mock-0.4.0',
      simulated: 1,
    });
    const t = getLatestTelemetry();
    expect(t).not.toBeNull();
    expect(t!.temperature_c).toBe(27.5);
    expect(t!.humidity_pct).toBe(54);
  });

  it('upserts device state with all fields', () => {
    upsertDeviceState({
      device_id: 'bedroom-ac-01',
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
    expect(s).not.toBeNull();
    expect(s!.availability).toBe('online');
    expect(s!.power_reported).toBe(1);
    expect(s!.target_temperature_reported).toBe(26);
  });

  it('inserts a command, marks ack, and reads it back', () => {
    const command_id = 'test-cmd-001';
    insertCommand({
      command_id,
      device_id: 'bedroom-ac-01',
      action: 'set_state',
      requested_power: 1,
      requested_temperature_c: 26,
      status: 'pending',
      created_at: Date.now(),
      expires_at: Date.now() + 120000,
    });
    updateCommandAck(command_id, 'blocked_by_ir_policy', Date.now(), 'real_ir_control_disabled');
    const cmds = getRecentCommands(10);
    const c = cmds.find((x: any) => x.command_id === command_id);
    expect(c).toBeDefined();
    expect(c!.status).toBe('blocked_by_ir_policy');
  });

  it('upsertDeviceState with minimal fields does not throw', () => {
    expect(() =>
      upsertDeviceState({
        device_id: 'bedroom-ac-01',
        availability: 'online',
        last_seen_at: Date.now(),
        data_freshness: 'fresh',
        updated_at: Date.now(),
      })
    ).not.toThrow();
  });
});
