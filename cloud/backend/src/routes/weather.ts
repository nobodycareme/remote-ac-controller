import { FastifyInstance } from 'fastify';
import { fetchWeatherNow } from '../weather';
import { requireAuth } from '../guards';
import { config } from '../config';

export async function registerWeatherRoutes(fastify: FastifyInstance): Promise<void> {
  // Xi'an outdoor weather (Open-Meteo, cached + stale fallback).
  fastify.get('/api/weather', { preHandler: requireAuth }, async (_req, reply) => {
    try {
      const w = await fetchWeatherNow();
      reply.send({
        city: config.WEATHER_CITY,
        latitude: config.WEATHER_LATITUDE,
        longitude: config.WEATHER_LONGITUDE,
        ...w,
      });
    } catch (e: any) {
      reply.code(502).send({ error: 'weather_unavailable', detail: e?.message });
    }
  });
}
