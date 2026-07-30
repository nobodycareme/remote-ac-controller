import { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { v4 as uuid } from 'uuid';
import { dispatchCommand, dispatchIrAction, productionIrControlEnabled } from '../mqtt_bridge';
import { requireAuth, requireAuthCsrf, requireOrigin, requireOwnerCsrf, getRequestSession } from '../guards';
import { deny } from '../reply_utils';
import {
  insertEvent,
  getAcStateRows,
  getAcStateRow,
  setAcStateEnabled,
  insertAcSchedule,
  updateAcSchedule,
  deleteAcSchedule,
  listAcSchedules,
  getAcSchedule,
  getTemperatureRule,
  upsertTemperatureRule,
  listAutomationExecutions,
} from '../db';
import { DEFAULT_AUTOMATION_ON_STATE, DEFAULT_AUTOMATION_OFF_STATE } from '../ac_states';
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
// 2026-07-28 集成轮：白名单不再硬编码单一 codeId，改为查 ac_states 目录表
// （11 状态，启动时由 AC_STATES 同步入库；enabled 为运行期独立启停开关）。
function lookupDispatchableState(stateId: string): { ok: boolean; errorCode?: string; message?: string; row?: any } {
  const row = getAcStateRow(stateId);
  if (!row) return { ok: false, errorCode: 'UNKNOWN_STATE', message: `未知的空调状态：${stateId}` };
  if (!row.enabled) return { ok: false, errorCode: 'STATE_DISABLED', message: `该空调状态已被禁用：${stateId}`, row };
  return { ok: true, row };
}

function serializeStateRow(row: any) {
  return {
    stateId: row.state_id,
    displayName: row.display_name,
    mode: row.mode,
    temperature: Number(row.temperature),
    fan: row.fan,
    swingVertical: !!row.swing_vertical,
    swingHorizontal: !!row.swing_horizontal,
    powerOn: !!row.power_on,
    frameLength: Number(row.frame_length),
    frameSha256: row.frame_sha256,
    enabled: !!row.enabled,
  };
}

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
    if (!productionIrControlEnabled()) {
      await deny(reply, 403, 'REAL_IR_DISABLED', '真实红外发射已关闭（REAL_IR_PRODUCTION_CONTROL_ENABLED=false）', { ir_control: 'disabled' });
      return;
    }
    const parsed = irSchema.safeParse(req.body);
    if (!parsed.success) {
      reply.code(400).send({ error: 'invalid_ir_command', detail: parsed.error.issues.map((i) => i.message) });
      return;
    }
    const { ir_code_id } = parsed.data;
    const lookup = lookupDispatchableState(ir_code_id);
    if (!lookup.ok) {
      await deny(reply, lookup.errorCode === 'UNKNOWN_STATE' ? 400 : 403, lookup.errorCode!, lookup.message!, { ir_control: 'disabled' });
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

  // ── 状态目录（2026-07-28 集成轮）──────────────────────────────────────────
  // 只读列表对所有会话开放（访客可见状态目录，但不能下发）。
  fastify.get('/api/ac/states', { preHandler: [requireAuth] }, async (_req, reply) => {
    const rows = getAcStateRows();
    reply.send({
      states: rows.map(serializeStateRow),
      ir_armed: productionIrControlEnabled(),
    });
  });

  // 单状态启停开关 —— Owner 专属。
  fastify.patch('/api/ac/states/:stateId', { preHandler: [requireOrigin, requireOwnerCsrf] }, async (req, reply) => {
    const stateId = String((req.params as any).stateId ?? '');
    const body = z.object({ enabled: z.boolean() }).safeParse(req.body);
    if (!body.success) {
      reply.code(400).send({ error: 'invalid_body', detail: body.error.issues.map((i) => i.message) });
      return;
    }
    const row = getAcStateRow(stateId);
    if (!row) {
      reply.code(404).send({ error: 'unknown_state', message: `未知的空调状态：${stateId}` });
      return;
    }
    setAcStateEnabled(stateId, body.data.enabled);
    insertEvent('ac_state_toggle', config.DEVICE_ID, `state=${stateId} enabled=${body.data.enabled}`);
    reply.send({ ok: true, state: serializeStateRow(getAcStateRow(stateId)) });
  });

  // ── 定时任务 CRUD ─────────────────────────────────────────────────────────
  const scheduleSchema = z.object({
    name: z.string().max(64).default(''),
    state_id: z.string().min(8).max(96),
    time_hhmm: z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/),
    days_mask: z.number().int().min(1).max(127).default(127),
    one_shot: z.boolean().default(false),
    enabled: z.boolean().default(true),
  });

  fastify.get('/api/ac/schedules', { preHandler: [requireAuth] }, async (_req, reply) => {
    reply.send({ schedules: listAcSchedules() });
  });

  fastify.post('/api/ac/schedules', { preHandler: [requireOrigin, requireOwnerCsrf] }, async (req, reply) => {
    const parsed = scheduleSchema.safeParse(req.body);
    if (!parsed.success) {
      reply.code(400).send({ error: 'invalid_schedule', detail: parsed.error.issues.map((i) => i.message) });
      return;
    }
    const chk = lookupDispatchableState(parsed.data.state_id);
    if (!chk.ok) {
      reply.code(400).send({ error: 'invalid_state', message: chk.message });
      return;
    }
    const session = getRequestSession(req);
    const id = insertAcSchedule({
      name: parsed.data.name,
      state_id: parsed.data.state_id,
      time_hhmm: parsed.data.time_hhmm,
      days_mask: parsed.data.days_mask,
      one_shot: parsed.data.one_shot ? 1 : 0,
      enabled: parsed.data.enabled ? 1 : 0,
      created_by: session?.user ?? 'owner',
    });
    insertEvent('ac_schedule_created', config.DEVICE_ID, `id=${id} state=${parsed.data.state_id} at=${parsed.data.time_hhmm}`);
    reply.send({ ok: true, schedule: getAcSchedule(id) });
  });

  fastify.patch('/api/ac/schedules/:id', { preHandler: [requireOrigin, requireOwnerCsrf] }, async (req, reply) => {
    const id = Number((req.params as any).id);
    const parsed = scheduleSchema.partial().safeParse(req.body);
    if (!Number.isInteger(id) || !parsed.success) {
      reply.code(400).send({ error: 'invalid_schedule', detail: parsed.success ? ['invalid id'] : parsed.error.issues.map((i) => i.message) });
      return;
    }
    if (parsed.data.state_id) {
      const chk = lookupDispatchableState(parsed.data.state_id);
      if (!chk.ok) {
        reply.code(400).send({ error: 'invalid_state', message: chk.message });
        return;
      }
    }
    const patch: any = { ...parsed.data };
    if (typeof patch.one_shot === 'boolean') patch.one_shot = patch.one_shot ? 1 : 0;
    if (typeof patch.enabled === 'boolean') patch.enabled = patch.enabled ? 1 : 0;
    const ok = updateAcSchedule(id, patch);
    if (!ok) {
      reply.code(404).send({ error: 'schedule_not_found' });
      return;
    }
    insertEvent('ac_schedule_updated', config.DEVICE_ID, `id=${id}`);
    reply.send({ ok: true, schedule: getAcSchedule(id) });
  });

  fastify.delete('/api/ac/schedules/:id', { preHandler: [requireOrigin, requireOwnerCsrf] }, async (req, reply) => {
    const id = Number((req.params as any).id);
    if (!Number.isInteger(id) || !deleteAcSchedule(id)) {
      reply.code(404).send({ error: 'schedule_not_found' });
      return;
    }
    insertEvent('ac_schedule_deleted', config.DEVICE_ID, `id=${id}`);
    reply.send({ ok: true });
  });

  // ── 温控自动化规则 ────────────────────────────────────────────────────────
  const tempRuleSchema = z
    .object({
      enabled: z.boolean().optional(),
      on_threshold_c: z.number().min(18).max(35).optional(),
      off_threshold_c: z.number().min(16).max(33).optional(),
      on_state_id: z.string().min(8).max(96).optional(),
      off_state_id: z.string().min(8).max(96).optional(),
      min_interval_s: z.number().int().min(60).max(7200).optional(),
      sensor_stale_s: z.number().int().min(30).max(3600).optional(),
      manual_suppress_s: z.number().int().min(0).max(86400).optional(),
    })
    .superRefine((v, ctx) => {
      if (typeof v.on_threshold_c === 'number' && typeof v.off_threshold_c === 'number' && v.on_threshold_c <= v.off_threshold_c) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'on_threshold_c 必须大于 off_threshold_c（滞回区间）' });
      }
    });

  fastify.get('/api/ac/temperature-rule', { preHandler: [requireAuth] }, async (_req, reply) => {
    const rule = getTemperatureRule() ?? upsertTemperatureRule({}, {
      on_state_id: DEFAULT_AUTOMATION_ON_STATE,
      off_state_id: DEFAULT_AUTOMATION_OFF_STATE,
    });
    reply.send({ rule });
  });

  fastify.put('/api/ac/temperature-rule', { preHandler: [requireOrigin, requireOwnerCsrf] }, async (req, reply) => {
    const parsed = tempRuleSchema.safeParse(req.body);
    if (!parsed.success) {
      reply.code(400).send({ error: 'invalid_rule', detail: parsed.error.issues.map((i) => i.message) });
      return;
    }
    for (const key of ['on_state_id', 'off_state_id'] as const) {
      const sid = parsed.data[key];
      if (sid) {
        const chk = lookupDispatchableState(sid);
        if (!chk.ok) {
          reply.code(400).send({ error: 'invalid_state', message: chk.message });
          return;
        }
      }
    }
    // 合并现有规则做滞回区间整体校验（避免只改一个阈值时穿越另一个）。
    const existing = getTemperatureRule();
    const onT = parsed.data.on_threshold_c ?? Number(existing?.on_threshold_c ?? 28);
    const offT = parsed.data.off_threshold_c ?? Number(existing?.off_threshold_c ?? 26);
    if (onT <= offT) {
      reply.code(400).send({ error: 'invalid_rule', detail: ['on_threshold_c 必须大于 off_threshold_c（滞回区间）'] });
      return;
    }
    const patch: any = { ...parsed.data };
    if (typeof patch.enabled === 'boolean') patch.enabled = patch.enabled ? 1 : 0;
    const rule = upsertTemperatureRule(patch, {
      on_state_id: DEFAULT_AUTOMATION_ON_STATE,
      off_state_id: DEFAULT_AUTOMATION_OFF_STATE,
    });
    insertEvent('ac_temperature_rule_updated', config.DEVICE_ID, `enabled=${rule.enabled} on=${rule.on_threshold_c} off=${rule.off_threshold_c}`);
    reply.send({ ok: true, rule });
  });

  // ── 自动化执行审计 ────────────────────────────────────────────────────────
  fastify.get('/api/ac/automation/executions', { preHandler: [requireAuth] }, async (req, reply) => {
    const limit = Math.min(200, Math.max(1, Number((req.query as any)?.limit ?? 50) || 50));
    reply.send({ executions: listAutomationExecutions(limit) });
  });
}
