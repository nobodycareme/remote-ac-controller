import { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { getLatestTelemetry, getTelemetryHistory } from '../db';
import { requireAuth } from '../guards';

const rangeSchema = z.object({
  range: z.enum(['1h', '6h', '24h', '7d']).default('1h'),
});

const RANGE_MS: Record<string, number> = {
  '1h': 3600_000,
  '6h': 6 * 3600_000,
  '24h': 24 * 3600_000,
  '7d': 7 * 24 * 3600_000,
};

export async function registerTelemetryRoutes(fastify: FastifyInstance): Promise<void> {
  fastify.get('/api/telemetry/latest', { preHandler: requireAuth }, async (_req, reply) => {
    reply.send(getLatestTelemetry() ?? null);
  });

  fastify.get('/api/telemetry/history', { preHandler: requireAuth }, async (req, reply) => {
    const parsed = rangeSchema.safeParse(req.query);
    const range = parsed.success ? parsed.data.range : '1h';
    const points = getTelemetryHistory(RANGE_MS[range]);
    reply.send({ range, unit: '1min', points });
  });
}
