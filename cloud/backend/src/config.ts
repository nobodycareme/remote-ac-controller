import { z } from 'zod';

const schema = z.object({
  PORT: z.coerce.number().default(3100),
  HOST: z.string().default('0.0.0.0'),
  MQTT_URL: z.string().default('mqtt://remote-ac-broker:1883'),
  MQTT_USERNAME: z.string().default('remote-ac-backend'),
  MQTT_PASSWORD: z.string().default(''),
  DEVICE_ID: z.string().default('bedroom-ac-01'),
  TOPIC_PREFIX: z.string().default('remote-ac/v1/devices'),
  WEB_USER: z.string().default('admin'),
  WEB_PASSWORD: z.string().default(''),
  SESSION_SECRET: z.string().default('dev-secret-change-me'),
  SESSION_TTL_MIN: z.coerce.number().default(480),
  ALLOWED_ORIGINS: z.string().default(''),
  DB_PATH: z.string().default('./data/app.db'),
  WEATHER_CITY: z.string().default('西安市'),
  WEATHER_TIMEZONE: z.string().default('Asia/Shanghai'),
  WEATHER_LATITUDE: z.coerce.number().default(34.3416),
  WEATHER_LONGITUDE: z.coerce.number().default(108.9398),
  WEATHER_CACHE_MS: z.coerce.number().default(600000),
  WEATHER_STALE_MS: z.coerce.number().default(1800000),
});

export type Config = z.infer<typeof schema>;
export const config: Config = schema.parse(process.env);

export function topic(suffix: string): string {
  return `${config.TOPIC_PREFIX}/${config.DEVICE_ID}/${suffix}`;
}
