import { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { dispatchCommand } from '../mqtt_bridge';
import { requireAuthCsrf } from '../guards';
import { insertEvent } from '../db';
import { log } from '../logger';

const actionEnum = z.enum(['set_state', 'set_power', 'set_temperature']);

const cmdSchema = z
  .object({
    action: actionEnum,
    power: z.boolean().optional(),
    target_temperature_c: z.number().int().min(16).max(30).optional(),
  })
  .superRefine((val, ctx) => {
    if ((val.action === 'set_state' || val.action === 'set_temperature') && typeof val.target_temperature_c !== 'number') {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'target_temperature_c required for set_state/set_temperature (16-30)' });
    }
    if (val.action === 'set_power' && typeof val.power !== 'boolean') {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'power required (true/false) for set_power' });
    }
  });

export async function registerAcRoutes(fastify: FastifyInstance): Promise<void> {
  // Issue a control command to the device. CSRF-protected, requires session.
  // NOTE: real IR emission is disabled by device policy; the command is delivered
  // and the device returns an ACK (blocked_by_ir_policy) — the loop is real, the
  // physical IR actuation is intentionally NOT performed.
  fastify.post('/api/ac/command', { preHandler: requireAuthCsrf }, async (req, reply) => {
    const parsed = cmdSchema.safeParse(req.body);
    if (!parsed.success) {
      reply.code(400).send({ error: 'invalid_command', detail: parsed.error.issues.map((i) => i.message) });
      return;
    }
    const { action, power, target_temperature_c } = parsed.data;
    const res = dispatchCommand(action, { power, target_temperature_c });
    log.info('command dispatched', { ...res, action });
    insertEvent('command_dispatched', 'bedroom-ac-01', `action=${action} status=${res.status}`);
    reply.send({ command_id: res.command_id, status: res.status, action, ir_control: 'disabled' });
  });
}
