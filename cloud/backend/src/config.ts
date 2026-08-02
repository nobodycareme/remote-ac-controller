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
  // Temporary no-login debug switch for the real-IR field lab. MUST be parsed as a
  // strict boolean: only the literal strings "true"/"1" enable it. NOTE:
  // z.coerce.boolean() is UNSAFE here because Boolean("false") === true (any
  // non-empty string is truthy), which would silently keep the debug portal ON
  // when an operator sets WEB_REAL_IR_ENABLED=false.
  WEB_REAL_IR_ENABLED: z
    .string()
    .default('false')
    .transform((s) => {
      const v = String(s).trim().toLowerCase();
      return v === 'true' || v === '1';
    }),
  // Separate production control flag for trusted owner sessions.
  REAL_IR_PRODUCTION_CONTROL_ENABLED: z
    .string()
    .default('false')
    .transform((s) => {
      const v = String(s).trim().toLowerCase();
      return v === 'true' || v === '1';
    }),
  // No-login real-IR field debug window. Safe default is OFF. Set
  // REAL_IR_DEBUG_EXPIRES_AT to time-box it; leave it blank for permanent mode.
  REAL_IR_DEBUG_MODE: z
    .string()
    .default('false')
    .transform((s) => {
      const v = String(s).trim().toLowerCase();
      return v === 'true' || v === '1';
    }),
  // Empty string means the debug window is permanent when REAL_IR_DEBUG_MODE=true.
  REAL_IR_DEBUG_EXPIRES_AT: z.string().default(''),
  // Debug-path allow-list. Empty by default: the debug transmit route stays
  // closed until an operator explicitly names one code id, its SHA-256 digest
  // and its frame length. There is intentionally no appliance-specific
  // fallback here.
  REAL_IR_DEBUG_ALLOWED_CODE_ID: z.string().default(''),
  REAL_IR_DEBUG_ALLOWED_CODE_SHA256: z.string().default(''),
  REAL_IR_DEBUG_ALLOWED_CODE_LENGTH: z.coerce.number().default(0),
  // 0 (or less) means unlimited transmissions while the window remains open.
  REAL_IR_DEBUG_MAX_TOTAL_COMMANDS: z.coerce.number().default(3),
  // 0 disables the inter-shot cooldown.
  REAL_IR_DEBUG_COOLDOWN_SECONDS: z.coerce.number().default(10),
  REAL_IR_DEBUG_COMMAND_TTL_SECONDS: z.coerce.number().default(30),
  REAL_IR_DEBUG_SESSION_TTL_SECONDS: z.coerce.number().default(3600),
  // WEB_USER and WEB_PASSWORD are the only Owner login credentials. Legacy
  // IR_OWNER_* environment variables are intentionally not part of the schema
  // and therefore cannot enable or alter Owner authorization.
  // Long-lived trusted owner-device sessions. Default is one year.
  TRUSTED_OWNER_SESSION_TTL_DAYS: z.coerce.number().default(365),
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
