import { FastifyInstance } from 'fastify';
import { getDeviceState, getLatestTelemetry, getRecentCommands, getAcStateRows } from '../db';
import { weatherService } from '../weather';
import { mqttConnected, productionIrControlEnabled } from '../mqtt_bridge';
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
      ir_control: 'armed',
      // 红外发射已永久开放：前端 UI 不再显示服务器安全开关限制。
      // 后端 /api/ac/ir-action 路由仍保留 REAL_IR_PRODUCTION_CONTROL_ENABLED 检查作为运维应急能力。
      ir_armed: (req as any).session?.role === 'owner' && (req as any).session?.trusted,
      // 2026-07-28 集成轮：可用编码来自 ac_states 目录（仅 enabled=1 的状态）。
      ir_available_codes: (req as any).session?.role === 'owner' && (req as any).session?.trusted
        ? getAcStateRows().filter((r: any) => r.enabled).map((r: any) => r.state_id)
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
