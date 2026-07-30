import { FastifyInstance } from 'fastify';
import { weatherService } from '../weather';
import { requireAuth } from '../guards';

export async function registerWeatherRoutes(fastify: FastifyInstance): Promise<void> {
  // Xi'an outdoor weather (Open-Meteo), served independently of the device.
  // Returns 200 with the last known snapshot even if the device is offline,
  // MQTT is down, or no telemetry has ever arrived. (Task §十四)
  fastify.get('/api/weather/current', { preHandler: requireAuth }, async (_req, reply) => {
    const w = weatherService.getSnapshot();
    if (!w) {
      // Not yet fetched on this process; trigger a refresh and tell the client.
      weatherService.refresh().catch(() => {});
      reply.code(503).send({ ok: false, errorCode: 'WEATHER_NOT_READY', message: '天气数据尚未就绪，请稍后重试' });
      return;
    }
    reply.send({
      ok: true,
      location: {
        name: w.city,
        latitude: w.latitude,
        longitude: w.longitude,
        timezone: w.timezone,
      },
      current: {
        temperatureC: w.temperature_2m,
        relativeHumidity: w.relative_humidity_2m,
        apparentTemperatureC: w.apparent_temperature,
        weatherCode: w.weather_code,
        windSpeed: w.wind_speed_10m,
        isDay: w.is_day,
      },
      observedAt: w.observed_at,
      fetchedAt: w.fetched_at,
      lastSuccessAt: w.last_success_at,
      nextRefreshAt: w.next_refresh_at,
      stale: w.stale,
      source: w.source,
      error: w.error,
    });
  });

  // Legacy alias kept for backward compatibility.
  fastify.get('/api/weather', { preHandler: requireAuth }, async (_req, reply) => {
    const w = weatherService.getSnapshot();
    if (!w) {
      reply.code(502).send({ error: 'weather_unavailable' });
      return;
    }
    reply.send({ ...w });
  });
}
