import { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { v4 as uuid } from 'uuid';
import { dispatchCommand, dispatchIrAction, irControlEnabled } from '../mqtt_bridge';
import { requireAuthCsrf, requireOrigin, requireOwnerCsrf, getRequestSession } from '../guards';
import { deny } from '../reply_utils';
import { insertEvent } from '../db';
import { config } from '../config';
import { log } from '../logger';

const actionEnum = z.enum(['set_state', 'set_power', 'set_temperature']);

// Client-generated Idempotency-Key: alphanumeric, dash, underscore; 16..128 chars. No secrets.
const idemSchema = z
  .string()
  .regex(/^[A-Za-z0-9_-]{16,128}$/)
  .optional();

const cmdSchema = z
  .object({
    action: actionEnum,
    power: z.boolean().optional(),
    target_temperature_c: z.number().int().min(16).max(30).optional(),
    idempotency_key: idemSchema,
  })
  .superRefine((val, ctx) => {
    if ((val.action === 'set_state' || val.action === 'set_temperature') && typeof val.target_temperature_c !== 'number') {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'target_temperature_c required for set_state/set_temperature (16-30)' });
    }
    if (val.action === 'set_power' && typeof val.power !== 'boolean') {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'power required (true/false) for set_power' });
    }
  });

// Allowed real-IR vendor codes (must match PROGMEM registry in firmware).
// Owner-gated: even listing is fine, but emission requires owner + WEB_REAL_IR_ENABLED.
const IR_CODE_IDS = new Set<string>([
  'hisense_cool_24_quiet_swing_v_on_swing_h_on_power_on_v1',
]);

export async function registerAcRoutes(fastify: FastifyInstance): Promise<void> {
  // Issue a control command to the device. CSRF-protected, requires session.
  // NOTE: real IR emission is disabled by device policy; the command is delivered
  // and the device returns an ACK (blocked_by_ir_policy) — the loop is real, the
  // physical IR actuation is intentionally NOT performed.
  fastify.post('/api/ac/command', { preHandler: [requireOrigin, requireAuthCsrf] }, async (req, reply) => {
    const parsed = cmdSchema.safeParse(req.body);
    if (!parsed.success) {
      reply.code(400).send({ error: 'invalid_command', detail: parsed.error.issues.map((i) => i.message) });
      return;
    }
    const { action, power, target_temperature_c } = parsed.data;
    // Use client key if provided, else mint a fresh one (each request stays unique).
    const idempotencyKey = parsed.data.idempotency_key ?? uuid();

    const res = dispatchCommand(action, { power, target_temperature_c }, idempotencyKey);

    if (res.offline_rejected) {
      reply.code(409).send({ error: 'device_offline', message: '设备离线，无法下发命令', ir_control: 'disabled' });
      return;
    }

    // Strict idempotency: same key + different payload must NOT reuse the first command.
    if (res.payload_mismatch) {
      reply.code(409).send({
        error: 'idempotency_key_payload_mismatch',
        message: '相同幂等键但请求体不同，拒绝复用首条命令',
        idempotency_replay: true,
        command_id: res.command_id,
        ir_control: 'disabled',
      });
      return;
    }

    // Only record a dispatch event for a genuinely new command (not an idempotent replay).
    if (!res.idempotency_replay) {
      insertEvent('command_dispatched', 'bedroom-ac-01', `action=${action} status=${res.status} idem=${idempotencyKey}`);
      log.info('command dispatched', { command_id: res.command_id, action, idempotency_key: idempotencyKey });
    } else {
      log.info('command idempotent replay served', { command_id: res.command_id, action, idempotency_key: idempotencyKey });
    }

    reply.send({
      command_id: res.command_id,
      status: res.status,
      action,
      idempotency_key: idempotencyKey,
      idempotency_replay: !!res.idempotency_replay,
      ir_control: 'disabled',
    });
  });

  // Real-IR action — OWNER ONLY (Section 七/八/九). Requires valid Origin + owner
  // session + CSRF. Guests / unauth / CSRF / origin failures are denied upstream.
  const irSchema = z.object({
    ir_code_id: z.string().min(8).max(96),
    idempotency_key: idemSchema,
  });

  fastify.post('/api/ac/ir-action', { preHandler: [requireOrigin, requireOwnerCsrf] }, async (req, reply) => {
    // Master kill switch — even an owner cannot emit when this is false.
    if (!irControlEnabled()) {
      await deny(reply, 403, 'REAL_IR_DISABLED', '真实红外发射已关闭（WEB_REAL_IR_ENABLED=false）', { ir_control: 'disabled' });
      return;
    }
    const parsed = irSchema.safeParse(req.body);
    if (!parsed.success) {
      reply.code(400).send({ error: 'invalid_ir_command', detail: parsed.error.issues.map((i) => i.message) });
      return;
    }
    const { ir_code_id } = parsed.data;
    if (!IR_CODE_IDS.has(ir_code_id)) {
      reply.code(400).send({ error: 'unknown_ir_code', message: `未知的红外编码：${ir_code_id}` });
      return;
    }
    const idempotencyKey = parsed.data.idempotency_key ?? uuid();
    const session = getRequestSession(req);
    const requestedBy = session?.user ?? 'owner';

    const res = dispatchIrAction(ir_code_id, { requested_by: requestedBy, idempotency_key: idempotencyKey });

    if (res.ir_disabled) {
      await deny(reply, 403, 'REAL_IR_DISABLED', '真实红外发射已关闭', { ir_control: 'disabled' });
      return;
    }
    if (res.offline_rejected) {
      await deny(reply, 409, 'DEVICE_OFFLINE', '设备离线，无法下发红外命令', { ir_control: 'disabled' });
      return;
    }
    if (res.idempotency_replay && res.status === 'idempotency_key_payload_mismatch') {
      await deny(reply, 409, 'IDEMPOTENCY_KEY_PAYLOAD_MISMATCH', '相同幂等键但请求体不同，拒绝复用首条命令', {
        idempotency_replay: true,
        command_id: res.command_id,
        ir_control: 'armed',
      });
      return;
    }

    if (!res.idempotency_replay) {
      insertEvent('ir_command_dispatched', 'bedroom-ac-01', `code=${ir_code_id} status=${res.status} idem=${idempotencyKey}`);
      log.info('ir action dispatched', { command_id: res.command_id, ir_code_id, requested_by: requestedBy });
    } else {
      log.info('ir action idempotent replay served', { command_id: res.command_id, ir_code_id });
    }

    reply.send({
      command_id: res.command_id,
      status: res.status,
      ir_code_id,
      idempotency_key: idempotencyKey,
      idempotency_replay: !!res.idempotency_replay,
      ir_control: 'armed',
    });
  });
}
