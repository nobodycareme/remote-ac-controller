/**
 * 纯展示逻辑库（无副作用，可单测）。
 * 商业化 UI 升级：所有"技术字段 → 人类可读文案"的转换集中在这里。
 */

export const DAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];

export const MODE_LABELS: Record<string, string> = {
  cool: '制冷',
  dry: '除湿',
  heat: '制热',
  off: '电源',
};

export const FAN_LABELS: Record<string, string> = {
  auto: '自动风',
  turbo: '超强风',
  quiet: '静音风',
};

/** 绝对时间戳（unix ms / 数字字符串）→ YYYY-MM-DD HH:mm；非法输入返回 '--'。 */
export function formatTimestamp(ts: number | string | null | undefined): string {
  if (ts === null || ts === undefined || ts === '') return '--';
  const n = typeof ts === 'string' ? Number(ts) : ts;
  if (!Number.isFinite(n) || n <= 0) return '--';
  const d = new Date(n);
  if (Number.isNaN(d.getTime())) return '--';
  const p = (x: number) => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 相对时间：刚刚 / N 分钟前 / N 小时前 / N 天前。now 可注入便于测试。 */
export function relativeTime(ts: number | null | undefined, now: number = Date.now()): string {
  if (!ts || !Number.isFinite(ts) || ts <= 0) return '--';
  const s = Math.max(0, Math.floor((now - ts) / 1000));
  if (s < 60) return '刚刚';
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`;
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`;
  return `${Math.floor(s / 86400)} 天前`;
}

// ===== 受信任设备：User-Agent → 中文人类可读设备信息 =====

export interface DeviceInfo {
  /** 设备类型中文名：Windows 电脑 / Mac 电脑 / iPhone / iPad / Android 手机 / Android 平板 / Linux 电脑 / 未知设备 */
  device: string;
  /** 浏览器中文名：Microsoft Edge / Opera / Google Chrome / Mozilla Firefox / Safari / 微信 / 浏览器 */
  browser: string;
}

/**
 * 从 User-Agent 提取人类可读设备信息。
 * 浏览器识别顺序（规格第八节，Edg 必须先于 Chrome）：
 *   微信内置 → Edg/ → OPR/ → Chrome/ → Firefox/ → Version/+Safari/ → 浏览器
 * 设备识别顺序：iPhone → iPad → Android(Mobile/平板) → Windows NT → Macintosh → Linux → 未知设备
 * 注意：Windows NT 10.0 无法可靠区分 Win10/Win11，统一显示"Windows 电脑"。
 */
export function parseUserAgent(ua: string | null | undefined): DeviceInfo {
  const s = String(ua ?? '');

  let browser = '浏览器';
  if (/MicroMesse/i.test(s)) browser = '微信'; // 微信内置浏览器（含 120 字符截断后的 MicroMesse）
  else if (/Edg\//.test(s)) browser = 'Microsoft Edge';
  else if (/OPR\//.test(s)) browser = 'Opera';
  else if (/Chrome\//.test(s)) browser = 'Google Chrome';
  else if (/Firefox\//.test(s)) browser = 'Mozilla Firefox';
  else if (/Version\//.test(s) && /Safari\//.test(s)) browser = 'Safari';

  let device = '未知设备';
  if (/iPhone/.test(s)) device = 'iPhone';
  else if (/iPad/.test(s)) device = 'iPad';
  else if (/Android/.test(s)) device = /Mobile/.test(s) ? 'Android 手机' : 'Android 平板';
  else if (/Windows NT/.test(s)) device = 'Windows 电脑';
  else if (/Macintosh/.test(s)) device = 'Mac 电脑';
  else if (/Linux/.test(s)) device = 'Linux 电脑';

  return { device, browser };
}

export interface TrustStatusInput {
  revoked?: boolean;
  persistent?: boolean;
  expiresAt?: number | null;
}

/**
 * 信任状态显示规则（规格第十节，顺序固定）：
 * revoked → 已撤销；persistent → 长期有效；expiresAt>0 → 有效至 YYYY-MM-DD HH:mm；否则 → 状态未知。
 * createdAt / trustedAt / lastLoginAt 一律不得传入 expiresAt。
 */
export function trustStatusText(input: TrustStatusInput): string {
  if (input.revoked) return '已撤销';
  if (input.persistent) return '长期有效';
  if (input.expiresAt !== null && input.expiresAt !== undefined && Number(input.expiresAt) > 0) {
    return `有效至 ${formatTimestamp(input.expiresAt)}`;
  }
  return '状态未知';
}

/** days_mask（bit0=周一 … bit6=周日）→ 人类可读。 */
export function daysMaskText(mask: number): string {
  if (mask === 127) return '每天';
  if (mask === 31) return '工作日';
  if (mask === 96) return '周末';
  const out: string[] = [];
  for (let i = 0; i < 7; i++) if (mask & (1 << i)) out.push('周' + DAY_LABELS[i]);
  return out.join(' ');
}

/** 星期勾选数组 → days_mask。 */
export function buildDaysMask(days: boolean[]): number {
  let mask = 0;
  days.forEach((d, i) => {
    if (d) mask |= 1 << i;
  });
  return mask;
}

/** HH:MM 24 小时制校验。 */
export function isValidHHMM(v: string): boolean {
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(v);
}

/** 定时任务表单校验；返回 null 表示通过，否则返回人类可读错误。 */
export function validateScheduleForm(f: { state_id: string; time_hhmm: string; days: boolean[] }): string | null {
  if (!f.state_id) return '请选择要执行的空调状态。';
  if (!isValidHHMM(f.time_hhmm)) return '请输入有效的 24 小时制时间（HH:MM）。';
  if (buildDaysMask(f.days) === 0) return '请至少选择一个重复的星期。';
  return null;
}

/** 温控阈值校验：开启阈值必须严格高于关闭阈值。 */
export function validateRuleThresholds(onC: number, offC: number): string | null {
  if (!Number.isFinite(onC) || !Number.isFinite(offC)) return '阈值必须是有效数字。';
  if (!(onC > offC)) return '开机阈值必须高于关机阈值（保持滞回区间，避免频繁开关）。';
  return null;
}

/** Open-Meteo weather code → 中文描述。 */
export function weatherText(code: number): string {
  const m: Record<number, string> = {
    0: '晴', 1: '大致晴朗', 2: '局部多云', 3: '阴', 45: '雾', 48: '雾凇',
    51: '小雨', 53: '小雨', 55: '中雨', 61: '小雨', 63: '中雨', 65: '大雨',
    71: '小雪', 73: '中雪', 75: '大雪', 80: '阵雨', 95: '雷阵雨',
  };
  return m[code] ?? '未知';
}

/** Open-Meteo weather code → 图标名（供 AppIcon 使用）。 */
export function weatherIconName(code: number): string {
  if (code === 0 || code === 1) return 'sun';
  if (code === 2) return 'cloud-sun';
  if (code === 3) return 'cloud';
  if (code === 45 || code === 48) return 'fog';
  if ([51, 53, 55, 61, 63, 65, 80].includes(code)) return 'rain';
  if ([71, 73, 75].includes(code)) return 'snow';
  if (code === 95) return 'storm';
  return 'cloud';
}

export interface StateLike {
  stateId: string;
  displayName: string;
  mode: string;
  temperature: number;
  fan: string | null;
  swingVertical: boolean;
  swingHorizontal: boolean;
  powerOn: boolean;
  enabled: boolean;
}

/** 状态副标签：风速 + 扫风的人类可读组合。 */
export function stateChipText(s: Pick<StateLike, 'fan' | 'swingVertical' | 'swingHorizontal'>): string {
  const parts: string[] = [];
  if (s.fan) parts.push(FAN_LABELS[s.fan] ?? s.fan);
  if (s.swingVertical && s.swingHorizontal) parts.push('双向扫风');
  else if (s.swingVertical) parts.push('上下扫风');
  else if (s.swingHorizontal) parts.push('左右扫风');
  return parts.join(' · ');
}

/** 按 off→cool→dry→heat 顺序对状态分组（保持既有业务顺序）。 */
export function groupStatesByMode<T extends { mode: string }>(states: T[]): { mode: string; label: string; states: T[] }[] {
  const order = ['off', 'cool', 'dry', 'heat'];
  const groups: { mode: string; label: string; states: T[] }[] = [];
  for (const m of order) {
    const list = states.filter((s) => s.mode === m);
    if (list.length) groups.push({ mode: m, label: MODE_LABELS[m] ?? m, states: list });
  }
  return groups;
}

export interface ExecutionLike {
  source: string;
  state_id: string;
  status: string;
  detail?: string | null;
  created_at: number;
}

/**
 * 自动化执行记录 → 人类可读一句话。
 * 注意准确性：只描述"系统发送了红外指令"，不声称空调实际响应（红外为单向）。
 */
export function humanizeExecution(e: ExecutionLike, stateName: (id: string) => string): { title: string; ok: boolean } {
  const src = e.source === 'schedule' ? '定时任务' : '温度自动化';
  const name = stateName(e.state_id);
  if (e.status === 'dispatched') {
    return { title: `${src}已发送「${name}」红外指令`, ok: true };
  }
  const reason = humanizeExecutionDetail(e.detail);
  return { title: `${src}尝试执行「${name}」未发送${reason ? '：' + reason : ''}`, ok: false };
}

/** 技术 detail → 人类可读原因。未识别的原文透传（保证信息不丢失）。 */
export function humanizeExecutionDetail(detail: string | null | undefined): string {
  if (!detail) return '';
  const map: [RegExp, string][] = [
    [/min_interval/i, '距上次自动操作时间过短，已按安全间隔跳过'],
    [/manual_suppress/i, '你刚手动操作过，自动化暂停期内跳过'],
    [/sensor_stale/i, '室温数据过旧，为安全起见未执行'],
    [/device_offline/i, '设备离线，指令未发送'],
    [/ir_policy|REAL_IR_DISABLED/i, '红外发射当前被安全开关禁用'],
    [/duplicate|already/i, '目标状态与当前一致，无需重复发送'],
  ];
  for (const [re, text] of map) if (re.test(detail)) return text;
  return detail;
}

/** 设备可用性 → 人类可读状态与语气。 */
export function availabilityHuman(a: string | undefined | null): { text: string; tone: 'ok' | 'bad' | 'warn' } {
  if (a === 'online') return { text: '设备在线', tone: 'ok' };
  if (a === 'offline') return { text: '设备离线', tone: 'bad' };
  return { text: '状态未知', tone: 'warn' };
}

/**
 * 真实红外发射门控（纯函数，可单测）：
 * 服务器开关开启 + 设备在线 + 云端通道连接 + 受信任 Owner + 非忙碌，全部满足才可发射。
 * 注意：这只是前端显示层门控，服务端仍有独立强制校验（不可绕过）。
 */
export function computeCanFireRealIr(f: {
  irArmed: boolean;
  online: boolean;
  mqttConnected: boolean;
  trustedOwner: boolean;
  busy: boolean;
}): boolean {
  return f.irArmed && f.online && f.mqttConnected && f.trustedOwner && !f.busy;
}

/** RSSI → 信号强度分档。 */
export function rssiHuman(rssi: number | null | undefined): string {
  if (rssi === null || rssi === undefined || !Number.isFinite(rssi)) return '--';
  if (rssi >= -55) return '信号极好';
  if (rssi >= -67) return '信号良好';
  if (rssi >= -75) return '信号一般';
  return '信号较弱';
}
