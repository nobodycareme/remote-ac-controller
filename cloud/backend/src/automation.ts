// ── AC 自动化 Worker（2026-07-28 全量集成轮）──────────────────────────────────
// 单一定时扫描器（10s），驱动两类自动化：
//   1. 定时任务（ac_schedules）：Asia/Shanghai 本地 HH:MM + 星期掩码触发状态下发；
//      同一分钟幂等（last_fired_minute 锚点），one_shot 触发后自动禁用。
//   2. 温控自动化（ac_temperature_rules）：双阈值滞回（默认 开≥28℃ / 关≤26℃），
//      3 样本中位数 + 连续 2 次评估一致才动作；护栏：
//        - 传感器陈旧（最新样本 > sensor_stale_s）→ 不动作
//        - 最短启停间隔 min_interval_s（默认 600s）
//        - 手动命令抑制窗口 manual_suppress_s（默认 1800s）
//        - 设备离线 / 主 kill switch 关闭 → dispatchIrAction 内部拒绝并审计
// 所有真实下发均走统一 dispatchIrAction（与手动路径同一 Command Service：
// 幂等键、TTL、离线门禁、REAL_IR_PRODUCTION_CONTROL_ENABLED 主开关全部生效）。
// requested_by = 'automation:schedule:<id>' / 'automation:temperature:<id>'，
// 该前缀同时是手动抑制窗口判定的排除标记（db.getLastManualIrCommandAt）。
import { dispatchIrAction } from './mqtt_bridge';
import {
  listEnabledAcSchedules,
  markAcScheduleFired,
  getAcStateRow,
  getTemperatureRule,
  recordTemperatureRuleAction,
  recordTemperatureRuleEval,
  insertAutomationExecution,
  getRecentTelemetrySamples,
  getLastManualIrCommandAt,
  insertEvent,
} from './db';
import { log } from './logger';

export const AUTOMATION_SCAN_INTERVAL_MS = 10_000;

let timer: ReturnType<typeof setInterval> | null = null;

// 温控「连续 2 次评估一致」内存状态（进程重启即归零，安全侧）。
let pendingAction: 'on' | 'off' | null = null;
let pendingCount = 0;

// ── 时间工具（Asia/Shanghai，避免依赖服务器时区设置）────────────────────────
const fmt = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  hour: '2-digit', minute: '2-digit', hour12: false,
  year: 'numeric', month: '2-digit', day: '2-digit',
  weekday: 'short',
});

interface LocalNow {
  hhmm: string;        // "07:30"
  minuteKey: string;   // "2026-07-28T07:30" —— 分钟幂等锚点
  dayBit: number;      // bit0=周一 … bit6=周日
}

export function getLocalNow(date = new Date()): LocalNow {
  const parts = fmt.formatToParts(date);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
  const hh = get('hour').padStart(2, '0');
  const mm = get('minute').padStart(2, '0');
  const weekday = get('weekday'); // 周一…周日
  const dayIndexMap: Record<string, number> = { 周一: 0, 周二: 1, 周三: 2, 周四: 3, 周五: 4, 周六: 5, 周日: 6 };
  const dayBit = 1 << (dayIndexMap[weekday] ?? 0);
  const minuteKey = `${get('year')}-${get('month')}-${get('day')}T${hh}:${mm}`;
  return { hhmm: `${hh}:${mm}`, minuteKey, dayBit };
}

function median(values: number[]): number {
  const s = values.slice().sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

// ── 状态可用性检查（目录级 enabled 开关）────────────────────────────────────
function stateDispatchable(stateId: string): { ok: boolean; reason: string } {
  const row = getAcStateRow(stateId);
  if (!row) return { ok: false, reason: `unknown_state:${stateId}` };
  if (!row.enabled) return { ok: false, reason: `state_disabled:${stateId}` };
  return { ok: true, reason: '' };
}

// ── 统一下发（带审计）────────────────────────────────────────────────────────
function dispatchForAutomation(
  source: 'schedule' | 'temperature',
  ruleId: number,
  stateId: string,
  idempotencyKey: string,
): { dispatched: boolean; status: string; command_id?: string } {
  const chk = stateDispatchable(stateId);
  if (!chk.ok) {
    insertAutomationExecution({ source, rule_id: ruleId, state_id: stateId, status: 'skipped_state_unavailable', detail: chk.reason });
    return { dispatched: false, status: chk.reason };
  }
  const res = dispatchIrAction(stateId, {
    requested_by: `automation:${source}:${ruleId}`,
    idempotency_key: idempotencyKey,
  });
  if (res.ir_disabled) {
    insertAutomationExecution({ source, rule_id: ruleId, state_id: stateId, status: 'skipped_ir_disabled', detail: 'REAL_IR_PRODUCTION_CONTROL_ENABLED=false' });
    return { dispatched: false, status: 'ir_disabled' };
  }
  if (res.offline_rejected) {
    insertAutomationExecution({ source, rule_id: ruleId, state_id: stateId, status: 'skipped_device_offline', detail: '' });
    return { dispatched: false, status: 'device_offline' };
  }
  insertAutomationExecution({
    source, rule_id: ruleId, state_id: stateId,
    command_id: res.command_id,
    status: res.idempotency_replay ? 'idempotent_replay' : 'dispatched',
    detail: `status=${res.status}`,
  });
  insertEvent(`automation_${source}_dispatched`, 'bedroom-ac-01', `rule=${ruleId} state=${stateId} cmd=${res.command_id}`);
  log.info('automation dispatched', { source, ruleId, stateId, command_id: res.command_id, status: res.status });
  return { dispatched: true, status: res.status, command_id: res.command_id };
}

// ── 定时任务扫描 ─────────────────────────────────────────────────────────────
export function scanSchedules(now = new Date()): void {
  const local = getLocalNow(now);
  const rows = listEnabledAcSchedules();
  for (const s of rows) {
    if (s.time_hhmm !== local.hhmm) continue;
    if (!(Number(s.days_mask) & local.dayBit)) continue;
    if (s.last_fired_minute === local.minuteKey) continue; // 同分钟幂等
    // 先记账再下发：即使下发失败，也不会在同一分钟内风暴重试（下一分钟窗口关闭）。
    markAcScheduleFired(Number(s.id), local.minuteKey, Number(s.one_shot) === 1);
    dispatchForAutomation('schedule', Number(s.id), String(s.state_id), `auto-sched-${s.id}-${local.minuteKey}`);
  }
}

// ── 温控自动化扫描（双阈值滞回）──────────────────────────────────────────────
export function scanTemperatureRule(now = Date.now()): void {
  const rule = getTemperatureRule();
  if (!rule || !rule.enabled) {
    pendingAction = null;
    pendingCount = 0;
    return;
  }
  const ruleId = Number(rule.id);

  const samples = getRecentTelemetrySamples(3);
  if (samples.length < 3) {
    recordTemperatureRuleEval(ruleId, 'insufficient_samples');
    pendingAction = null; pendingCount = 0;
    return;
  }
  const newest = samples[0];
  const staleMs = Number(rule.sensor_stale_s) * 1000;
  if (now - Number(newest.server_received_at) > staleMs) {
    recordTemperatureRuleEval(ruleId, 'sensor_stale');
    pendingAction = null; pendingCount = 0;
    return;
  }
  const temp = median(samples.map((s) => Number(s.temperature_c)));

  // 滞回判定
  let desired: 'on' | 'off' | null = null;
  if (temp >= Number(rule.on_threshold_c)) desired = 'on';
  else if (temp <= Number(rule.off_threshold_c)) desired = 'off';
  if (!desired) {
    recordTemperatureRuleEval(ruleId, `in_deadband:${temp.toFixed(1)}C`);
    pendingAction = null; pendingCount = 0;
    return;
  }
  // 与上次已执行动作相同 → 无需重复
  if (rule.last_action === desired) {
    recordTemperatureRuleEval(ruleId, `already_${desired}:${temp.toFixed(1)}C`);
    pendingAction = null; pendingCount = 0;
    return;
  }
  // 最短启停间隔
  if (rule.last_action_at && now - Number(rule.last_action_at) < Number(rule.min_interval_s) * 1000) {
    recordTemperatureRuleEval(ruleId, `min_interval_hold:${desired}`);
    return;
  }
  // 手动抑制窗口
  const lastManual = getLastManualIrCommandAt();
  if (lastManual && now - lastManual < Number(rule.manual_suppress_s) * 1000) {
    recordTemperatureRuleEval(ruleId, `manual_suppressed:${desired}`);
    return;
  }
  // 连续 2 次评估一致才动作
  if (pendingAction === desired) {
    pendingCount += 1;
  } else {
    pendingAction = desired;
    pendingCount = 1;
  }
  if (pendingCount < 2) {
    recordTemperatureRuleEval(ruleId, `pending_confirm_${desired}:${pendingCount}/2`);
    return;
  }
  pendingAction = null;
  pendingCount = 0;

  const stateId = desired === 'on' ? String(rule.on_state_id) : String(rule.off_state_id);
  const minuteAnchor = Math.floor(now / 60_000);
  const r = dispatchForAutomation('temperature', ruleId, stateId, `auto-temp-${ruleId}-${desired}-${minuteAnchor}`);
  if (r.dispatched) {
    recordTemperatureRuleAction(ruleId, desired, `median=${temp.toFixed(1)}C -> ${desired}`);
  }
}

// ── Worker 生命周期 ─────────────────────────────────────────────────────────
export function startAutomationWorker(): void {
  if (timer) return;
  timer = setInterval(() => {
    try {
      scanSchedules();
      scanTemperatureRule();
    } catch (e: any) {
      log.error('automation scan error', { err: e?.message });
    }
  }, AUTOMATION_SCAN_INTERVAL_MS);
  // Node 定时器不阻止进程退出
  (timer as any).unref?.();
  log.info('automation worker started', { interval_ms: AUTOMATION_SCAN_INTERVAL_MS });
}

export function stopAutomationWorker(): void {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
  pendingAction = null;
  pendingCount = 0;
}

// 测试钩子：重置内存判定状态
export function _resetTemperatureConfirmState(): void {
  pendingAction = null;
  pendingCount = 0;
}
