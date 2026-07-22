// Typed API client for the remote-ac-cloud backend.
const BASE = '/api';

export interface SessionInfo {
  authenticated: boolean;
  user?: string;
  role?: string;
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
export function getCsrf(): string | null {
  return csrfToken;
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {};
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

export async function login(username: string, password: string): Promise<SessionInfo> {
  const r = await req<{ ok: boolean; csrf: string; user: string; role?: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  csrfToken = r.csrf;
  return { authenticated: true, user: r.user, role: r.role ?? 'owner', csrf: r.csrf };
}

export async function logout(): Promise<void> {
  await req('/auth/logout', { method: 'POST' });
  csrfToken = null;
}

export async function fetchDashboard(): Promise<Dashboard> {
  return req<Dashboard>('/dashboard');
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

// Real-IR action (Section 九). Owner-only; requires WEB_REAL_IR_ENABLED=true on the
// server. Sends a vendor PROGMEM code id; the device emits the raw 22H frame once.
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
