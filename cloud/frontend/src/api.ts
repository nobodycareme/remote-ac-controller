// Typed API client for the remote-ac-cloud backend.
const BASE = '/api';

export interface SessionInfo {
  authenticated: boolean;
  user?: string;
  csrf?: string;
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
    let detail = '';
    try {
      detail = (await res.json())?.detail || (await res.json())?.error || '';
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchSession(): Promise<SessionInfo> {
  return req<SessionInfo>('/auth/session');
}

export async function login(username: string, password: string): Promise<SessionInfo> {
  const r = await req<{ ok: boolean; csrf: string; user: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  csrfToken = r.csrf;
  return { authenticated: true, user: r.user, csrf: r.csrf };
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

export interface CommandResult {
  command_id: string;
  status: string;
  action: string;
  ir_control: string;
}

export async function sendCommand(action: 'set_state' | 'set_power' | 'set_temperature', opts: { power?: boolean; target_temperature_c?: number }): Promise<CommandResult> {
  return req<CommandResult>('/ac/command', {
    method: 'POST',
    body: JSON.stringify({ action, ...opts }),
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
