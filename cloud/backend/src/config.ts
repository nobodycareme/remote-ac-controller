import { z } from 'zod';

const schema = z.object({
  PORT: z.coerce.number().default(3100),
  HOST: z.string().default('127.0.0.1'),
  MQTT_URL: z.string().default('mqtt://remote-ac-broker:1883'),
  MQTT_USERNAME: z.string().default('remote-ac-backend'),
  MQTT_PASSWORD: z.string().default(''),
  DEVICE_ID: z.string().default('bedroom-ac-01'),
  TOPIC_PREFIX: z.string().default('remote-ac/v1/devices'),
  WEB_USER: z.string().default('admin'),
  WEB_PASSWORD: z.string().default(''),
  SESSION_SECRET: z.string().default('dev-secret-change-me'),
  SESSION_TTL_MIN: z.coerce.number().default(480),
  ALLOWED_ORIGINS: z.string().default('https://ac.example.com'),
  PUBLIC_BASE_URL: z.string().default('https://ac.example.com'),
  DB_PATH: z.string().default('./data/app.db'),
  WEATHER_CITY: z.string().default('西安市'),
  WEATHER_TIMEZONE: z.string().default('Asia/Shanghai'),
  WEATHER_LATITUDE: z.coerce.number().default(34.3416),
  WEATHER_LONGITUDE: z.coerce.number().default(108.9398),
  WEATHER_CACHE_MS: z.coerce.number().default(600000),
  WEATHER_STALE_MS: z.coerce.number().default(1800000),
  // Independent WeatherService refresh cadence (ms). Weather is decoupled from the
  // device entirely: this timer runs on its own from process start, independent of
  // any telemetry, MQTT, or device-online state.
  WEATHER_REFRESH_MS: z.coerce.number().default(600000),
  ACCESS_MODE: z.enum(['login_required', 'public_guest']).default('public_guest'),
  // ── Real-IR safety gate (Section 七/八/九) ──────────────────────────────
  // Master kill switch for ANY real infrared emission triggered from the web.
  // DEFAULT FALSE: even an Owner session cannot emit IR unless this is explicitly
  // set to true. This is the single runtime control that arms real IR.
  // Real-IR master kill switch. MUST be parsed as a strict boolean: only the
  // literal strings "true"/"1" enable IR. NOTE: z.coerce.boolean() is UNSAFE here
  // because Boolean("false") === true (any non-empty string is truthy), which would
  // silently keep the kill switch ON when an operator sets WEB_REAL_IR_ENABLED=false.
  // We parse the raw string explicitly so "false"/"0"/""/"off" all mean disabled.
  WEB_REAL_IR_ENABLED: z
    .string()
    .default('false')
    .transform((s) => {
      const v = String(s).trim().toLowerCase();
      return v === 'true' || v === '1';
    }),
  // Owner credentials for the privileged IR-action path. In public_guest mode a
  // guest session is auto-created (role='guest', no IR). An owner session
  // (role='owner') is minted only by /api/auth/login with the correct password.
  IR_OWNER_USER: z.string().default('admin'),
  IR_OWNER_PASSWORD: z.string().default(''),
  // Idempotency / replay window for IR commands (ms). A command older than this
  // (or a duplicate command_id) is rejected. Mirrors the firmware exec-cache TTL
  // (IR_EXEC_TTL_MS=30000) so the backend and device agree on the window.
  IR_COMMAND_TTL_MS: z.coerce.number().default(25000),
  // Offline / stale thresholds for command gating and UI badges.
  // A device is considered offline if availability != 'online' OR last_seen_at older than this.
  OFFLINE_THRESHOLD_MS: z.coerce.number().default(90000),
  // Telemetry older than this is shown as "数据已陈旧" (stale) in the UI.
  STALE_THRESHOLD_MS: z.coerce.number().default(60000),
  // Real device reporting intervals — mirror firmware src/cloud/telemetry_service.h
  // (PUBLISH_INTERVAL_MS=5000, DHT_MIN_INTERVAL_MS=2500). Displayed verbatim in the UI;
  // do NOT substitute suggested values.
  DEVICE_PUBLISH_INTERVAL_MS: z.coerce.number().default(5000),
  DEVICE_SAMPLE_INTERVAL_MS: z.coerce.number().default(2500),
});

export type Config = z.infer<typeof schema>;
export const config: Config = schema.parse(process.env);

export function topic(suffix: string): string {
  return `${config.TOPIC_PREFIX}/${config.DEVICE_ID}/${suffix}`;
}
