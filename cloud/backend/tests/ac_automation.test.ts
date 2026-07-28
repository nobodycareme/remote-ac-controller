// ── 2026-07-28 集成轮：状态目录 + 定时任务 + 温控滞回自动化测试 ────────────────
import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest';

// dispatchIrAction 打桩：不触真实 MQTT，仅记录调用。
const dispatchCalls: Array<{ stateId: string; opts: any }> = [];
let dispatchResult: any = { command_id: 'cmd-auto-1', status: 'pending', ir_code_id: '', idempotency_replay: false, mqtt_published: true };

vi.mock('../src/mqtt_bridge', () => ({
  dispatchIrAction: (stateId: string, opts: any) => {
    dispatchCalls.push({ stateId, opts });
    return { ...dispatchResult, ir_code_id: stateId };
  },
  productionIrControlEnabled: () => true,
}));

import {
  initDb,
  syncAcStates,
  getAcStateRows,
  getAcStateRow,
  setAcStateEnabled,
  insertAcSchedule,
  listEnabledAcSchedules,
  getAcSchedule,
  upsertTemperatureRule,
  getTemperatureRule,
  insertTelemetry,
  listAutomationExecutions,
  getDb,
} from '../src/db';
import { AC_STATES, getAcState, DEFAULT_AUTOMATION_ON_STATE, DEFAULT_AUTOMATION_OFF_STATE } from '../src/ac_states';
import { scanSchedules, scanTemperatureRule, getLocalNow, _resetTemperatureConfirmState } from '../src/automation';

function insertTempSample(tempC: number, at: number): void {
  insertTelemetry({
    device_id: 'bedroom-ac-01',
    seq: at % 100000,
    server_received_at: at,
    temperature_c: tempC,
    humidity_pct: 50,
    sensor_ok: 1,
    wifi_rssi_dbm: -50,
    free_heap_bytes: 20000,
    uptime_s: 10,
    wifi_reconnect_count: 0,
    mqtt_reconnect_count: 0,
    mqtt_initial_connect_count: 1,
    mqtt_reconnect_attempt_count: 0,
    mqtt_reconnect_success_count: 0,
    firmware_version: 'test',
    simulated: 0,
  });
}

beforeAll(() => {
  initDb();
  syncAcStates(AC_STATES.map((s) => ({ ...s })));
});

beforeEach(() => {
  dispatchCalls.length = 0;
  _resetTemperatureConfirmState();
  getDb().exec('DELETE FROM telemetry');
  getDb().exec('DELETE FROM commands');
  getDb().exec('DELETE FROM ac_schedules');
  getDb().exec('DELETE FROM ac_temperature_rules');
  getDb().exec('DELETE FROM ac_automation_executions');
});

// ── 状态目录 ──────────────────────────────────────────────────────────────────
describe('ac_states catalog', () => {
  it('has exactly 11 states, all enabled by default', () => {
    const rows = getAcStateRows();
    expect(rows.length).toBe(11);
    expect(rows.every((r: any) => r.enabled === 1)).toBe(true);
  });

  it('fixed CAPTURE_002 baseline metadata is intact', () => {
    const row = getAcStateRow('hisense_cool_24_quiet_swing_v_on_swing_h_on_power_on_v1');
    expect(row).toBeTruthy();
    expect(row.frame_length).toBe(418);
    expect(row.frame_sha256).toBe('e9ab43feca71acde248df5729d0cb0d228bdbcfb69f8513d43ea4b942cb6ac7e');
  });

  it('per-state enable toggle persists and survives re-sync', () => {
    expect(setAcStateEnabled('hisense_heat_28_auto_swingVH_v1', false)).toBe(true);
    expect(getAcStateRow('hisense_heat_28_auto_swingVH_v1').enabled).toBe(0);
    // 再次同步（模拟重启）不得覆盖运行期开关
    syncAcStates(AC_STATES.map((s) => ({ ...s })));
    expect(getAcStateRow('hisense_heat_28_auto_swingVH_v1').enabled).toBe(0);
    setAcStateEnabled('hisense_heat_28_auto_swingVH_v1', true);
  });

  it('code catalog and DB rows agree on stateIds', () => {
    const dbIds = new Set(getAcStateRows().map((r: any) => r.state_id));
    for (const s of AC_STATES) expect(dbIds.has(s.stateId)).toBe(true);
    expect(getAcState('hisense_power_off_v1')?.mode).toBe('off');
  });
});

// ── 定时任务 ──────────────────────────────────────────────────────────────────
describe('schedule scanning', () => {
  it('fires a matching schedule exactly once per minute (idempotent anchor)', () => {
    const now = new Date();
    const local = getLocalNow(now);
    insertAcSchedule({
      name: 't1', state_id: DEFAULT_AUTOMATION_ON_STATE, time_hhmm: local.hhmm,
      days_mask: 127, one_shot: 0, enabled: 1, created_by: 'test',
    });
    scanSchedules(now);
    scanSchedules(now); // 同分钟第二次扫描不得重复触发
    expect(dispatchCalls.length).toBe(1);
    expect(dispatchCalls[0].stateId).toBe(DEFAULT_AUTOMATION_ON_STATE);
    expect(dispatchCalls[0].opts.requested_by).toMatch(/^automation:schedule:/);
    const execs = listAutomationExecutions();
    expect(execs.some((e: any) => e.source === 'schedule' && e.status === 'dispatched')).toBe(true);
  });

  it('does not fire when time does not match', () => {
    const now = new Date();
    const local = getLocalNow(now);
    const otherTime = local.hhmm === '00:00' ? '00:01' : '00:00';
    insertAcSchedule({
      name: 't2', state_id: DEFAULT_AUTOMATION_ON_STATE, time_hhmm: otherTime,
      days_mask: 127, one_shot: 0, enabled: 1, created_by: 'test',
    });
    scanSchedules(now);
    expect(dispatchCalls.length).toBe(0);
  });

  it('does not fire when today is excluded from days_mask', () => {
    const now = new Date();
    const local = getLocalNow(now);
    insertAcSchedule({
      name: 't3', state_id: DEFAULT_AUTOMATION_ON_STATE, time_hhmm: local.hhmm,
      days_mask: 127 & ~local.dayBit, one_shot: 0, enabled: 1, created_by: 'test',
    });
    scanSchedules(now);
    expect(dispatchCalls.length).toBe(0);
  });

  it('one_shot schedule disables itself after firing', () => {
    const now = new Date();
    const local = getLocalNow(now);
    const id = insertAcSchedule({
      name: 't4', state_id: 'hisense_power_off_v1', time_hhmm: local.hhmm,
      days_mask: 127, one_shot: 1, enabled: 1, created_by: 'test',
    });
    scanSchedules(now);
    expect(dispatchCalls.length).toBe(1);
    expect(getAcSchedule(id).enabled).toBe(0);
    expect(listEnabledAcSchedules().length).toBe(0);
  });

  it('skips disabled states and records the skip', () => {
    const now = new Date();
    const local = getLocalNow(now);
    setAcStateEnabled('hisense_cool_25_auto_v1', false);
    insertAcSchedule({
      name: 't5', state_id: 'hisense_cool_25_auto_v1', time_hhmm: local.hhmm,
      days_mask: 127, one_shot: 0, enabled: 1, created_by: 'test',
    });
    scanSchedules(now);
    expect(dispatchCalls.length).toBe(0);
    const execs = listAutomationExecutions();
    expect(execs.some((e: any) => e.status === 'skipped_state_unavailable')).toBe(true);
    setAcStateEnabled('hisense_cool_25_auto_v1', true);
  });
});

// ── 温控自动化（双阈值滞回）────────────────────────────────────────────────────
describe('temperature hysteresis automation', () => {
  const defaults = { on_state_id: DEFAULT_AUTOMATION_ON_STATE, off_state_id: DEFAULT_AUTOMATION_OFF_STATE };

  function freshRule(patch: any = {}) {
    return upsertTemperatureRule({ enabled: 1, ...patch }, defaults);
  }

  function seedSamples(temps: number[], now: number) {
    temps.forEach((t, i) => insertTempSample(t, now - (temps.length - 1 - i) * 5000));
  }

  it('turns ON after two consecutive confirmations above on-threshold', () => {
    freshRule();
    const now = Date.now();
    seedSamples([28.6, 28.4, 28.8], now);
    scanTemperatureRule(now);      // 第 1 次确认
    expect(dispatchCalls.length).toBe(0);
    scanTemperatureRule(now + 10_000); // 第 2 次确认 → 动作
    expect(dispatchCalls.length).toBe(1);
    expect(dispatchCalls[0].stateId).toBe(DEFAULT_AUTOMATION_ON_STATE);
    expect(getTemperatureRule().last_action).toBe('on');
  });

  it('holds inside the deadband (26–28℃)', () => {
    freshRule();
    const now = Date.now();
    seedSamples([27.0, 27.2, 26.9], now);
    scanTemperatureRule(now);
    scanTemperatureRule(now + 10_000);
    expect(dispatchCalls.length).toBe(0);
    expect(getTemperatureRule().last_eval_reason).toMatch(/in_deadband/);
  });

  it('does not act on stale sensor data', () => {
    freshRule({ sensor_stale_s: 180 });
    const now = Date.now();
    seedSamples([29.0, 29.1, 29.2], now - 400_000); // 全部超过 180s
    scanTemperatureRule(now);
    scanTemperatureRule(now + 10_000);
    expect(dispatchCalls.length).toBe(0);
    expect(getTemperatureRule().last_eval_reason).toBe('sensor_stale');
  });

  it('uses 3-sample median (single spike does not trigger)', () => {
    freshRule();
    const now = Date.now();
    seedSamples([26.5, 35.0, 26.7], now); // 中位数 26.7 在死区
    scanTemperatureRule(now);
    scanTemperatureRule(now + 10_000);
    expect(dispatchCalls.length).toBe(0);
  });

  it('respects min_interval between actions', () => {
    const rule = freshRule({ min_interval_s: 600 });
    const now = Date.now();
    // 模拟 2 分钟前刚执行过 on
    getDb().prepare('UPDATE ac_temperature_rules SET last_action=?, last_action_at=? WHERE id=?')
      .run('on', now - 120_000, rule.id);
    seedSamples([25.0, 25.2, 24.9], now); // 应触发 off，但间隔不足
    scanTemperatureRule(now);
    scanTemperatureRule(now + 10_000);
    expect(dispatchCalls.length).toBe(0);
    expect(getTemperatureRule().last_eval_reason).toMatch(/min_interval_hold/);
  });

  it('is suppressed by a recent manual IR command', () => {
    freshRule({ manual_suppress_s: 1800, min_interval_s: 60 });
    const now = Date.now();
    // 手动命令（requested_by 非 automation: 前缀）
    getDb().prepare(`INSERT INTO commands (command_id, device_id, action, ir_code_id, status, created_at, expires_at, requested_by)
      VALUES (?, 'bedroom-ac-01', 'ir_action', 'hisense_cool_26_auto_v1', 'ir_executed', ?, ?, 'admin')`)
      .run('manual-1', now - 60_000, now - 35_000);
    seedSamples([29.0, 29.1, 28.9], now);
    scanTemperatureRule(now);
    scanTemperatureRule(now + 10_000);
    expect(dispatchCalls.length).toBe(0);
    expect(getTemperatureRule().last_eval_reason).toMatch(/manual_suppressed/);
  });

  it('automation-origin commands do NOT suppress (prefix exclusion)', () => {
    freshRule({ manual_suppress_s: 1800, min_interval_s: 60 });
    const now = Date.now();
    getDb().prepare(`INSERT INTO commands (command_id, device_id, action, ir_code_id, status, created_at, expires_at, requested_by)
      VALUES (?, 'bedroom-ac-01', 'ir_action', 'hisense_power_off_v1', 'ir_executed', ?, ?, 'automation:schedule:9')`)
      .run('auto-1', now - 60_000, now - 35_000);
    seedSamples([28.9, 29.0, 29.1], now);
    scanTemperatureRule(now);
    scanTemperatureRule(now + 10_000);
    expect(dispatchCalls.length).toBe(1);
  });

  it('turns OFF below off-threshold with confirmations', () => {
    const rule = freshRule({ min_interval_s: 60 });
    const now = Date.now();
    getDb().prepare('UPDATE ac_temperature_rules SET last_action=?, last_action_at=? WHERE id=?')
      .run('on', now - 120_000, rule.id);
    seedSamples([25.5, 25.4, 25.6], now);
    scanTemperatureRule(now);
    scanTemperatureRule(now + 10_000);
    expect(dispatchCalls.length).toBe(1);
    expect(dispatchCalls[0].stateId).toBe(DEFAULT_AUTOMATION_OFF_STATE);
    expect(getTemperatureRule().last_action).toBe('off');
  });

  it('does nothing when rule disabled', () => {
    freshRule({ enabled: 0 });
    const now = Date.now();
    seedSamples([30.0, 30.1, 30.2], now);
    scanTemperatureRule(now);
    scanTemperatureRule(now + 10_000);
    expect(dispatchCalls.length).toBe(0);
  });
});
