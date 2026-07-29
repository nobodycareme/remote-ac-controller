import { describe, it, expect } from 'vitest';
import {
  formatTimestamp,
  relativeTime,
  daysMaskText,
  buildDaysMask,
  isValidHHMM,
  validateScheduleForm,
  validateRuleThresholds,
  weatherText,
  weatherIconName,
  stateChipText,
  groupStatesByMode,
  humanizeExecution,
  humanizeExecutionDetail,
  availabilityHuman,
  computeCanFireRealIr,
  rssiHuman,
} from './format';

// ---------- formatTimestamp（防"整页空白"回归：observed_at 是 number，禁 .slice）----------
describe('formatTimestamp', () => {
  it('T01 数字 unix ms 正常格式化，不抛异常', () => {
    const out = formatTimestamp(new Date(2026, 6, 29, 10, 5).getTime());
    expect(out).toBe('2026-07-29 10:05');
  });
  it('T02 数字字符串也可格式化', () => {
    const ts = new Date(2026, 0, 2, 3, 4).getTime();
    expect(formatTimestamp(String(ts))).toBe('2026-01-02 03:04');
  });
  it('T03 null/undefined/空串/非法值返回 --', () => {
    expect(formatTimestamp(null)).toBe('--');
    expect(formatTimestamp(undefined)).toBe('--');
    expect(formatTimestamp('')).toBe('--');
    expect(formatTimestamp('abc')).toBe('--');
    expect(formatTimestamp(0)).toBe('--');
    expect(formatTimestamp(-5)).toBe('--');
  });
});

// ---------- relativeTime ----------
describe('relativeTime', () => {
  const now = 1_800_000_000_000;
  it('T04 60 秒内为「刚刚」', () => {
    expect(relativeTime(now - 30_000, now)).toBe('刚刚');
  });
  it('T05 分钟/小时/天分档正确', () => {
    expect(relativeTime(now - 5 * 60_000, now)).toBe('5 分钟前');
    expect(relativeTime(now - 3 * 3_600_000, now)).toBe('3 小时前');
    expect(relativeTime(now - 2 * 86_400_000, now)).toBe('2 天前');
  });
  it('T06 非法输入返回 --；未来时间按 0 秒处理为「刚刚」', () => {
    expect(relativeTime(null, now)).toBe('--');
    expect(relativeTime(0, now)).toBe('--');
    expect(relativeTime(now + 10_000, now)).toBe('刚刚');
  });
});

// ---------- days mask ----------
describe('daysMaskText / buildDaysMask', () => {
  it('T07 127=每天，31=工作日，96=周末', () => {
    expect(daysMaskText(127)).toBe('每天');
    expect(daysMaskText(31)).toBe('工作日');
    expect(daysMaskText(96)).toBe('周末');
  });
  it('T08 任意组合逐日列出（bit0=周一）', () => {
    expect(daysMaskText(0b0000101)).toBe('周一 周三');
    expect(daysMaskText(0b1000000)).toBe('周日');
  });
  it('T09 buildDaysMask 与 daysMaskText 往返一致', () => {
    const days = [true, false, true, false, false, false, true]; // 一/三/日
    const mask = buildDaysMask(days);
    expect(mask).toBe(0b1000101);
    expect(daysMaskText(mask)).toBe('周一 周三 周日');
  });
  it('T10 全 false 得 0', () => {
    expect(buildDaysMask([false, false, false, false, false, false, false])).toBe(0);
  });
});

// ---------- HH:MM 与表单校验 ----------
describe('isValidHHMM / validateScheduleForm', () => {
  it('T11 合法 24 小时制时间', () => {
    expect(isValidHHMM('00:00')).toBe(true);
    expect(isValidHHMM('23:59')).toBe(true);
    expect(isValidHHMM('07:05')).toBe(true);
  });
  it('T12 非法时间被拒绝', () => {
    expect(isValidHHMM('24:00')).toBe(false);
    expect(isValidHHMM('12:60')).toBe(false);
    expect(isValidHHMM('7:05')).toBe(false);
    expect(isValidHHMM('')).toBe(false);
  });
  it('T13 未选状态 → 报状态错误', () => {
    expect(validateScheduleForm({ state_id: '', time_hhmm: '08:00', days: [true, false, false, false, false, false, false] }))
      .toContain('状态');
  });
  it('T14 非法时间 → 报时间错误', () => {
    expect(validateScheduleForm({ state_id: 's1', time_hhmm: '25:00', days: [true, false, false, false, false, false, false] }))
      .toContain('时间');
  });
  it('T15 未选星期 → 报星期错误', () => {
    expect(validateScheduleForm({ state_id: 's1', time_hhmm: '08:00', days: [false, false, false, false, false, false, false] }))
      .toContain('星期');
  });
  it('T16 全部合法 → null', () => {
    expect(validateScheduleForm({ state_id: 's1', time_hhmm: '08:00', days: [true, true, true, true, true, false, false] }))
      .toBeNull();
  });
});

// ---------- 温控阈值滞回校验 ----------
describe('validateRuleThresholds', () => {
  it('T17 开机阈值高于关机阈值 → 通过', () => {
    expect(validateRuleThresholds(28, 26)).toBeNull();
  });
  it('T18 相等或倒挂 → 拒绝（防频繁开关）', () => {
    expect(validateRuleThresholds(26, 26)).not.toBeNull();
    expect(validateRuleThresholds(25, 27)).not.toBeNull();
  });
  it('T19 非数字 → 拒绝', () => {
    expect(validateRuleThresholds(NaN, 26)).not.toBeNull();
    expect(validateRuleThresholds(28, Infinity)).not.toBeNull();
  });
});

// ---------- 天气 ----------
describe('weatherText / weatherIconName', () => {
  it('T20 常见 weather code 映射', () => {
    expect(weatherText(0)).toBe('晴');
    expect(weatherText(3)).toBe('阴');
    expect(weatherText(95)).toBe('雷阵雨');
  });
  it('T21 未知 code 返回「未知」且图标兜底 cloud', () => {
    expect(weatherText(9999)).toBe('未知');
    expect(weatherIconName(9999)).toBe('cloud');
  });
  it('T22 图标分类正确', () => {
    expect(weatherIconName(0)).toBe('sun');
    expect(weatherIconName(2)).toBe('cloud-sun');
    expect(weatherIconName(61)).toBe('rain');
    expect(weatherIconName(73)).toBe('snow');
    expect(weatherIconName(95)).toBe('storm');
  });
});

// ---------- 状态展示 ----------
describe('stateChipText / groupStatesByMode', () => {
  it('T23 风速+扫风组合文案', () => {
    expect(stateChipText({ fan: 'turbo', swingVertical: true, swingHorizontal: false })).toBe('超强风 · 上下扫风');
    expect(stateChipText({ fan: 'auto', swingVertical: true, swingHorizontal: true })).toBe('自动风 · 双向扫风');
    expect(stateChipText({ fan: null, swingVertical: false, swingHorizontal: true })).toBe('左右扫风');
  });
  it('T24 分组顺序 off→cool→dry→heat 且空组剔除', () => {
    const groups = groupStatesByMode([
      { mode: 'heat' }, { mode: 'cool' }, { mode: 'cool' }, { mode: 'off' },
    ]);
    expect(groups.map((g) => g.mode)).toEqual(['off', 'cool', 'heat']);
    expect(groups[1].states.length).toBe(2);
    expect(groups[0].label).toBe('电源');
  });
});

// ---------- 执行记录人类化（准确性铁律：不声称空调实际响应）----------
describe('humanizeExecution / humanizeExecutionDetail', () => {
  const name = (id: string) => (id === 's1' ? '制冷 26℃' : id);
  it('T25 dispatched → 「已发送…红外指令」且 ok=true，不出现"已开机/已响应"', () => {
    const r = humanizeExecution({ source: 'schedule', state_id: 's1', status: 'dispatched', created_at: 1 }, name);
    expect(r.ok).toBe(true);
    expect(r.title).toBe('定时任务已发送「制冷 26℃」红外指令');
    expect(r.title).not.toMatch(/已开机|已响应|已执行成功/);
  });
  it('T26 非 dispatched → 未发送 + 原因', () => {
    const r = humanizeExecution({ source: 'rule', state_id: 's1', status: 'skipped', detail: 'min_interval', created_at: 1 }, name);
    expect(r.ok).toBe(false);
    expect(r.title).toContain('温度自动化');
    expect(r.title).toContain('未发送');
    expect(r.title).toContain('安全间隔');
  });
  it('T27 已知 detail 全部映射为人类可读', () => {
    expect(humanizeExecutionDetail('manual_suppress')).toContain('手动操作');
    expect(humanizeExecutionDetail('sensor_stale')).toContain('室温数据过旧');
    expect(humanizeExecutionDetail('device_offline')).toContain('设备离线');
    expect(humanizeExecutionDetail('blocked_by_ir_policy')).toContain('安全开关');
    expect(humanizeExecutionDetail('REAL_IR_DISABLED')).toContain('安全开关');
    expect(humanizeExecutionDetail('duplicate_state')).toContain('无需重复');
  });
  it('T28 未识别 detail 原文透传，空值返回空串', () => {
    expect(humanizeExecutionDetail('some_new_reason')).toBe('some_new_reason');
    expect(humanizeExecutionDetail(null)).toBe('');
    expect(humanizeExecutionDetail(undefined)).toBe('');
  });
});

// ---------- 可用性 / 信号 ----------
describe('availabilityHuman / rssiHuman', () => {
  it('T29 online/offline/未知三态与语气', () => {
    expect(availabilityHuman('online')).toEqual({ text: '设备在线', tone: 'ok' });
    expect(availabilityHuman('offline')).toEqual({ text: '设备离线', tone: 'bad' });
    expect(availabilityHuman(undefined)).toEqual({ text: '状态未知', tone: 'warn' });
  });
  it('T30 RSSI 分档', () => {
    expect(rssiHuman(-50)).toBe('信号极好');
    expect(rssiHuman(-60)).toBe('信号良好');
    expect(rssiHuman(-70)).toBe('信号一般');
    expect(rssiHuman(-85)).toBe('信号较弱');
    expect(rssiHuman(null)).toBe('--');
  });
});

// ---------- 真实红外发射门控（安全关键路径）----------
describe('computeCanFireRealIr', () => {
  const base = { irArmed: true, online: true, mqttConnected: true, trustedOwner: true, busy: false };
  it('T31 全条件满足 → true', () => {
    expect(computeCanFireRealIr(base)).toBe(true);
  });
  it('T32 任一条件不满足 → false（逐项验证）', () => {
    expect(computeCanFireRealIr({ ...base, irArmed: false })).toBe(false);
    expect(computeCanFireRealIr({ ...base, online: false })).toBe(false);
    expect(computeCanFireRealIr({ ...base, mqttConnected: false })).toBe(false);
    expect(computeCanFireRealIr({ ...base, trustedOwner: false })).toBe(false);
    expect(computeCanFireRealIr({ ...base, busy: true })).toBe(false);
  });
});
