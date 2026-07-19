import { FastifyInstance } from 'fastify';
import { getDeviceState, getLatestTelemetry, getRecentCommands } from '../db';
import { fetchWeatherNow } from '../weather';
import { mqttConnected } from '../mqtt_bridge';
import { requireAuth } from '../guards';
import { config } from '../config';

export async function registerDashboardRoutes(fastify: FastifyInstance): Promise<void> {
  // Aggregated dashboard snapshot.
  fastify.get('/api/dashboard', { preHandler: requireAuth }, async (_req, reply) => {
    const state = getDeviceState();
    const telemetry = getLatestTelemetry();
    const commands = getRecentCommands(10);
    let weather = null;
    let weather_error = null;
    try {
      weather = await fetchWeatherNow();
    } catch (e: any) {
      weather_error = e?.message;
    }
    reply.send({
      device_id: config.DEVICE_ID,
      availability: state?.availability ?? 'unknown',
      last_seen_at: state?.last_seen_at ?? null,
      data_freshness: state?.data_freshness ?? 'unknown',
      firmware_version: telemetry?.firmware_version ?? null,
      mqtt_backend_connected: mqttConnected(),
      latest_telemetry: telemetry ?? null,
      recent_commands: commands,
      weather: weather
        ? {
            city: config.WEATHER_CITY,
            temperature_2m: weather.temperature_2m,
            relative_humidity_2m: weather.relative_humidity_2m,
            apparent_temperature: weather.apparent_temperature,
            weather_code: weather.weather_code,
            wind_speed_10m: weather.wind_speed_10m,
            is_day: weather.is_day,
            time: weather.time,
            stale: weather.stale,
            source: weather.source,
          }
        : null,
      weather_error,
      ir_control: 'disabled',
    });
  });
}
