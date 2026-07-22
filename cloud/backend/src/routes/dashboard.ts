import { FastifyInstance } from 'fastify';
import { getDeviceState, getLatestTelemetry, getRecentCommands } from '../db';
import { weatherService } from '../weather';
import { mqttConnected, irControlEnabled } from '../mqtt_bridge';
import { evaluateDeviceLiveness } from '../device_liveness';
import { requireAuth } from '../guards';
import { config } from '../config';

export async function registerDashboardRoutes(fastify: FastifyInstance): Promise<void> {
  // Aggregated dashboard snapshot.
  fastify.get('/api/dashboard', { preHandler: requireAuth }, async (req, reply) => {
    const state = getDeviceState();
    const liveness = evaluateDeviceLiveness(state);
    const telemetry = getLatestTelemetry();
    const commands = getRecentCommands(10);
    let weather = null;
    let weather_error = null;
    // Weather is delivered from the independent WeatherService cache — never
    // fetched inline against device state. (Task §十一)
    const w = weatherService.getSnapshot();
    if (w) {
      weather = {
        city: config.WEATHER_CITY,
        temperature_2m: w.temperature_2m,
        relative_humidity_2m: w.relative_humidity_2m,
        apparent_temperature: w.apparent_temperature,
        weather_code: w.weather_code,
        wind_speed_10m: w.wind_speed_10m,
        is_day: w.is_day,
        time: w.time,
        stale: w.stale,
        source: w.source,
      };
    } else {
      weather_error = '天气数据尚未就绪';
    }
    reply.send({
      device_id: config.DEVICE_ID,
      // Trusted presence (shared with the command offline-gate).
      online: liveness.online,
      availability: state?.availability ?? 'unknown',
      availability_hint: liveness.availability_hint,
      last_seen_at: state?.last_seen_at ?? null,
      last_telemetry_at: state?.last_telemetry_at ?? null,
      data_freshness: liveness.data_freshness,
      liveness_reason: liveness.reason,
      mqtt_initial_connect_count: state?.mqtt_initial_connect_count ?? null,
      mqtt_reconnect_attempt_count: state?.mqtt_reconnect_attempt_count ?? null,
      mqtt_reconnect_success_count: state?.mqtt_reconnect_success_count ?? null,
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
      ir_control: irControlEnabled() ? 'armed' : 'disabled',
      // The real-IR button is armed ONLY when the kill switch is on AND the current
      // session is an OWNER. A guest (or unauthenticated) session must never see the
      // armed button — this was the root cause of the spurious 403 (Task §二/§五).
      ir_armed: irControlEnabled() && (req as any).session?.role === 'owner',
      ir_available_codes: irControlEnabled() && (req as any).session?.role === 'owner'
        ? ['hisense_cool_24_quiet_swing_v_on_swing_h_on_power_on_v1']
        : [],
      settings: {
        device_publish_interval_ms: config.DEVICE_PUBLISH_INTERVAL_MS,
        device_sample_interval_ms: config.DEVICE_SAMPLE_INTERVAL_MS,
        stale_threshold_ms: config.STALE_THRESHOLD_MS,
        offline_threshold_ms: config.OFFLINE_THRESHOLD_MS,
        idempotency_supported: true,
      },
    });
  });
}
