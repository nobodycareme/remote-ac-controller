import { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { getEvents } from '../db';
import { requireAuth } from '../guards';

const qSchema = z.object({ limit: z.coerce.number().int().min(1).max(200).default(50) });

export async function registerEventsRoutes(fastify: FastifyInstance): Promise<void> {
  fastify.get('/api/events', { preHandler: requireAuth }, async (req, reply) => {
    const parsed = qSchema.safeParse(req.query);
    const limit = parsed.success ? parsed.data.limit : 50;
    reply.send({ events: getEvents(limit) });
  });
}
