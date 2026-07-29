// Typed API client for the remote-ac-cloud backend.
const BASE = '/api';

export interface SessionInfo {
  authenticated: boolean;
  user?: string;
  role?: string;
  trusted?: boolean;
  /** true = 长期有效受信任会话（不因固定日期失效，可随时移除）。 */
  trusted_persistent?: boolean;
  /** 仅临时信任才有具体到期时间；长期信任为 null。 */
  trusted_expires_at?: number | null;
  trusted_label?: string | null;
  ir_control?: 'armed' | 'disabled';
  csrf?: string;
}

// Structured API error: carries the backend error envelope fields (status +
// errorCode + message) so the UI can show a precise stage instead of "403 ".
export class ApiError extends Error {
  status: number;
  errorCode?: string;
  constructor(message: string, status: number, errorCode?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.errorCode = errorCode;
  }
}

export interface Telemetry {
  seq: number;
  server_received_at: number;
  temperature_c: number;
  humidity_pct: number;
  sensor_ok: number;
  wifi_rssi_dbm: number;
  free_heap_bytes: number;
  uptime_s: number;
  wifi_reconnect_count: number;
  mqtt_reconnect_count: number;
  firmware_version: string;
  simulated: number;
}

export interface WeatherNow {
  city: string;
  temperature_2m: number;
  relative_humidity_2m: number;
  apparent_temperature: number;
  weather_code: number;
  wind_speed_10m: number;
  is_day: number;
  time: string;
  stale: boolean;
  source: string;
}

export interface CommandRow {
  command_id: string;
  action: string;
  requested_power: number;
  requested_temperature_c: number;
  status: string;
  created_at: number;
  acknowledged_at: number | null;
  failure_reason: string | null;
}

export interface Dashboard {
  availability: string;
  last_seen_at: number | null;
  data_freshness: string;
  firmware_version: string | null;
  mqtt_backend_connected: boolean;
  latest_telemetry: Telemetry | null;
  recent_commands: CommandRow[];
  weather: WeatherNow | null;
  weather_error: string | null;
  ir_control: string;
  ir_armed?: boolean;
  ir_available_codes?: string[];
}

let csrfToken: string | null = null;
let irDebugCsrfToken: string | null = null;
export function getCsrf(): string | null {
  return csrfToken;
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.headers && !(opts.headers instanceof Headers) && !Array.isArray(opts.headers)) {
    Object.assign(headers, opts.headers as Record<string, string>);
  }
  if (opts.body) headers['content-type'] = 'application/json';
  if (csrfToken && (opts.method || 'GET') !== 'GET') headers['x-csrf-token'] = csrfToken;
  const res = await fetch(BASE + path, { ...opts, headers, credentials: 'include' });
  if (res.status === 401) {
    csrfToken = null;
    throw new Error('unauthorized');
  }
  if (!res.ok) {
    // Read the body ONCE, then extract the structured envelope fields. Calling
    // res.json() twice (the old bug) consumed the stream the second time and threw,
    // which was swallowed by the catch and collapsed every error to a bare "403 ".
    let body: any = null;
    try {
      body = await res.json();
    } catch {
      try {
        body = await res.text();
      } catch {
        /* ignore */
      }
    }
    if (body && typeof body === 'object') {
      const message = body.message || body.error || body.detail || '';
      throw new ApiError(`${res.status} ${message}`.trim(), res.status, body.errorCode);
    }
    const text = typeof body === 'string' ? body : '';
    throw new ApiError(`${res.status} ${text}`.trim(), res.status);
  }
  return res.json() as Promise<T>;
}

export async function fetchSession(): Promise<SessionInfo> {
  const r = await req<SessionInfo & { csrf?: string }>('/auth/session');
  // Guest mode (no login) also receives a CSRF token; persist it so sendCommand
  // includes the x-csrf-token header. Without this, POST /ac/command returns 403.
  if (r.csrf) csrfToken = r.csrf;
  return r;
}

export async function login(password: string): Promise<SessionInfo> {
  const r = await req<SessionInfo & { ok: boolean }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
  if (r.csrf) csrfToken = r.csrf;
  return r;
}

export async function logout(): Promise<void> {
  await req('/auth/logout', { method: 'POST' });
  csrfToken = null;
}

export async function revokeTrustedDevice(): Promise<void> {
  await req('/auth/trusted-device/revoke', { method: 'POST' });
  csrfToken = null;
}

export async function revokeAllTrustedDevices(): Promise<{ ok: boolean; revoked: number }> {
  const r = await req<{ ok: boolean; revoked: number }>('/auth/trusted-devices/revoke-all', { method: 'POST' });
  csrfToken = null;
  return r;
}

export async function fetchDashboard(): Promise<Dashboard> {
  return req<Dashboard>('/dashboard');
}

export interface IrDebugStage {
  commandId: string;
  status: string;
  mqttPublished: boolean;
  deviceReceived: boolean;
  codeValidated: boolean;
  uartFrameWritten: boolean;
  moduleAcknowledged: boolean;
  acResponse: 'unknown';
}

export interface IrDebugStatus {
  ok: boolean;
  debugMode: boolean;
  debugWindowConfigured: boolean;
  expiresAt: string | null;
  expiresInSeconds: number | null;
  remainingCommands: number | null;
  maxCommands: number | null;
  allowedCodeId: string;
  codeLength: number;
  deviceOnline: boolean;
  deviceFresh: boolean;
  deviceFreshness: string;
  deviceLivenessReason: string;
  mqttBackendConnected: boolean;
  webRealIrEnabled: boolean;
  irReady: boolean;
  telemetryMetadataUsable: boolean;
  legacyModuleAckPass: boolean;
  irGateSource: string;
  codeIdMatch: boolean;
  codeLengthMatch: boolean;
  codeShaMatch: boolean;
  ir22hStructurePass: boolean;
  commandInFlight: boolean;
  cooldownActive: boolean;
  cooldownRemainingSeconds: number;
  commandTtlSeconds: number;
  transmitEnabled: boolean;
  latestDebugCommand: IrDebugStage | null;
  csrfHeader?: string;
  debugCsrf?: string;
}

export interface IrDebugTransmitResult {
  ok: boolean;
  requestId: string;
  commandId: string | null;
  commandCreated: boolean;
  mqttPublished: boolean;
  deviceReceived: boolean;
  codeValidated: boolean;
  uartFrameWritten: boolean;
  moduleAcknowledged: boolean;
  acResponse: 'unknown';
  status?: string;
  allowedCodeId?: string;
  expiresAt?: string;
}

export async function fetchIrDebugStatus(): Promise<IrDebugStatus> {
  const r = await req<IrDebugStatus>('/ir/debug/status');
  if (r.debugCsrf) irDebugCsrfToken = r.debugCsrf;
  return r;
}

export async function transmitIrDebugOnce(commandId: string, idempotencyKey: string): Promise<IrDebugTransmitResult> {
  if (!irDebugCsrfToken) {
    await fetchIrDebugStatus();
  }
  return req<IrDebugTransmitResult>('/ir/debug/transmit', {
    method: 'POST',
    headers: irDebugCsrfToken ? { 'x-ir-debug-csrf': irDebugCsrfToken } : {},
    body: JSON.stringify({ confirm: true, commandId, idempotencyKey }),
  });
}

export async function fetchTelemetryHistory(range: string): Promise<{ range: string; unit: string; points: { t: number; temperature_c: number; humidity_pct: number }[] }> {
  return req(`/telemetry/history?range=${range}`);
}

export async function fetchEvents(): Promise<{ events: { id: number; event_type: string; device_id: string; message: string; created_at: number }[] }> {
  return req('/events');
}

// Independent Xi'an weather (Open-Meteo) — decoupled from the device entirely.
// Returns the last known snapshot even when the device is offline / MQTT is down.
// (Task §十一/§十二/§十三) Backed by the backend WeatherService, not /api/dashboard.
export async function fetchWeatherCurrent(): Promise<any> {
  return req('/weather/current');
}

export interface CommandResult {
  command_id: string;
  status: string;
  action: string;
  ir_control: string;
}

export async function sendCommand(action: 'set_state' | 'set_power' | 'set_temperature', opts: { power?: boolean; target_temperature_c?: number }): Promise<CommandResult> {
  // Per-action Idempotency-Key so concurrent/retried requests collapse to one command.
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let hex = '';
  for (const b of bytes) hex += b.toString(16).padStart(2, '0');
  const idempotency_key = 'idem-' + hex; // 37 chars, [A-Za-z0-9_-]
  return req<CommandResult>('/ac/command', {
    method: 'POST',
    body: JSON.stringify({ action, ...opts, idempotency_key }),
  });
}

// Real-IR action. Owner-only; requires a trusted owner session and the
// production IR control flag on the server. Sends a vendor PROGMEM code id; the
// device emits the raw 22H frame once.
// Returns immediately after the device ACK — it does NOT confirm the AC physically
// responded (that is out of band), so the UI must keep AC status as "pending".
export interface IrActionResult extends CommandResult {
  ir_code_id: string;
}

export async function sendIrAction(ir_code_id: string): Promise<IrActionResult> {
  // Per-action Idempotency-Key.
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let hex = '';
  for (const b of bytes) hex += b.toString(16).padStart(2, '0');
  const idempotency_key = 'idem-' + hex; // 37 chars, [A-Za-z0-9_-]
  return req<IrActionResult>('/ac/ir-action', {
    method: 'POST',
    body: JSON.stringify({ ir_code_id, idempotency_key }),
  });
}

// ===== v0.5.0 全状态控制 / 定时 / 温控自动化 API =====

export interface AcStateInfo {
  stateId: string;
  displayName: string;
  mode: 'cool' | 'dry' | 'heat' | 'off' | string;
  temperature: number;
  fan: string;
  swingVertical: boolean;
  swingHorizontal: boolean;
  powerOn: boolean;
  frameLength: number;
  frameSha256: string;
  enabled: boolean;
}

export async function fetchAcStates(): Promise<{ states: AcStateInfo[]; ir_armed: boolean }> {
  return req('/ac/states');
}

export async function patchAcState(stateId: string, enabled: boolean): Promise<{ ok: boolean; state: AcStateInfo }> {
  return req(`/ac/states/${encodeURIComponent(stateId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  });
}

export interface AcSchedule {
  id: number;
  name: string;
  state_id: string;
  time_hhmm: string;
  days_mask: number;
  one_shot: number;
  enabled: number;
  last_fired_minute: string | null;
  last_fired_at: number | null;
  created_by: string | null;
  created_at: number;
  updated_at: number;
}

export async function fetchSchedules(): Promise<{ schedules: AcSchedule[] }> {
  return req('/ac/schedules');
}

export async function createSchedule(body: { name: string; state_id: string; time_hhmm: string; days_mask: number; one_shot?: boolean; enabled?: boolean }): Promise<{ ok: boolean; schedule: AcSchedule }> {
  return req('/ac/schedules', { method: 'POST', body: JSON.stringify(body) });
}

export async function updateSchedule(id: number, patch: Partial<{ name: string; state_id: string; time_hhmm: string; days_mask: number; one_shot: boolean; enabled: boolean }>): Promise<{ ok: boolean; schedule: AcSchedule }> {
  return req(`/ac/schedules/${id}`, { method: 'PATCH', body: JSON.stringify(patch) });
}

export async function deleteSchedule(id: number): Promise<{ ok: boolean }> {
  return req(`/ac/schedules/${id}`, { method: 'DELETE' });
}

export interface TemperatureRule {
  id: number;
  enabled: number;
  on_threshold_c: number;
  off_threshold_c: number;
  on_state_id: string;
  off_state_id: string;
  min_interval_s: number;
  sensor_stale_s: number;
  manual_suppress_s: number;
  last_action: string | null;
  last_action_at: number | null;
  last_eval_reason: string | null;
  last_eval_at: number | null;
}

export async function fetchTemperatureRule(): Promise<{ rule: TemperatureRule }> {
  return req('/ac/temperature-rule');
}

export async function putTemperatureRule(patch: Partial<{ enabled: boolean; on_threshold_c: number; off_threshold_c: number; on_state_id: string; off_state_id: string; min_interval_s: number }>): Promise<{ ok: boolean; rule: TemperatureRule }> {
  return req('/ac/temperature-rule', { method: 'PUT', body: JSON.stringify(patch) });
}

export interface AutomationExecution {
  id: number;
  source: string;
  rule_id: number | null;
  state_id: string;
  command_id: string | null;
  status: string;
  detail: string | null;
  created_at: number;
}

export async function fetchAutomationExecutions(limit = 30): Promise<{ executions: AutomationExecution[] }> {
  return req(`/ac/automation/executions?limit=${limit}`);
}

export function connectWS(onMessage: (type: string, payload: any) => void): WebSocket | null {
  try {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/api/ws`);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        onMessage(msg.type, msg.payload);
      } catch {
        /* ignore */
      }
    };
    return ws;
  } catch {
    return null;
  }
}
