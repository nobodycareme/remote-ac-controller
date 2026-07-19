import { FastifyInstance } from 'fastify';
import { getDeviceState, getLatestTelemetry, getRecentCommands } from '../db';
import { requireAuth } from '../guards';
import { config } from '../config';

export async function registerDeviceRoutes(fastify: FastifyInstance): Promise<void> {
  // Current device view: availability, last telemetry, last intent (command).
  fastify.get('/api/device/state', { preHandler: requireAuth }, async (_req, reply) => {
    const state = getDeviceState();
    const telemetry = getLatestTelemetry();
    const commands = getRecentCommands(5);
    const lastIntent = commands.find((c: any) => c.status === 'accepted_mock' || c.status === 'blocked_by_ir_policy');
    reply.send({
      device_id: config.DEVICE_ID,
      availability: state?.availability ?? 'unknown',
      last_seen_at: state?.last_seen_at ?? null,
      data_freshness: state?.data_freshness ?? 'unknown',
      firmware_version: telemetry?.firmware_version ?? null,
      last_telemetry: telemetry ?? null,
      last_intent: lastIntent
        ? {
            command_id: lastIntent.command_id,
            action: lastIntent.action,
            requested_power: lastIntent.requested_power,
            requested_temperature_c: lastIntent.requested_temperature_c,
            status: lastIntent.status,
            created_at: lastIntent.created_at,
          }
        : null,
      ir_control: 'disabled',
    });
  });
}
