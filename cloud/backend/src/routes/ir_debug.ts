import { FastifyInstance, FastifyReply } from 'fastify';
import { z } from 'zod';
import { config } from '../config';
import {
  countActiveIrCommands,
  countIrDebugWindowCommands,
  expireStaleIrDebugCommands,
  getCommand,
  getDeviceState,
  getIrDebugCommandByIdempotencyHash,
  getLatestIrDebugWindowCommand,
  getLatestTelemetry,
  getRecentCommands,
  insertEvent,
} from '../db';
import { evaluateDeviceLiveness } from '../device_liveness';
import {
  DEBUG_CSRF_HEADER,
  debugNotExpired,
  debugWindowConfigured,
  debugWindowKey,
  ensureDebugSession,
  parseDebugExpiresAt,
  sha256Hex,
  validateDebugSession,
} from '../ir_debug';
import { dispatchIrAction, debugIrControlEnabled, mqttConnected } from '../mqtt_bridge';
import { log } from '../logger';

const FIXED_CODE_ID = 'hisense_cool_24_quiet_swing_v_on_swing_h_on_power_on_v1';
const PUBLIC_ORIGIN = 'https://ac.example.com';

const transmitSchema = z.object({
  confirm: z.literal(true),
  commandId: z.string().uuid(),
  idempotencyKey: z.string().uuid(),
}).strict();

function expectedCodeId(): string {
  return config.REAL_IR_DEBUG_ALLOWED_CODE_ID || FIXED_CODE_ID;
}

function expectedCodeSha(): string {
  return String(config.REAL_IR_DEBUG_ALLOWED_CODE_SHA256 || '').trim().toLowerCase();
}

function expectedCodeLength(): number {
  return Number(config.REAL_IR_DEBUG_ALLOWED_CODE_LENGTH || 418);
}

function debugMaxCommands(): number {
  return Math.max(0, Number(config.REAL_IR_DEBUG_MAX_TOTAL_COMMANDS || 0));
}

function debugCommandLimitUnlimited(): boolean {
  return debugMaxCommands() <= 0;
}

function cooldownSeconds(): number {
  return Math.max(0, Number(config.REAL_IR_DEBUG_COOLDOWN_SECONDS || 0));
}

function ttlSeconds(): number {
  return Math.max(1, Number(config.REAL_IR_DEBUG_COMMAND_TTL_SECONDS || 30));
}

function getOrigin(req: any): string {
  const origin = req.headers.origin;
  return Array.isArray(origin) ? origin[0] : String(origin || '');
}

function exactPublicOrigin(req: any): boolean {
  return getOrigin(req) === PUBLIC_ORIGIN && config.PUBLIC_BASE_URL === PUBLIC_ORIGIN;
}

function baseEnvelope(requestId: string, commandId: string | null = null) {
  return {
    requestId,
    commandId,
    commandCreated: false,
    mqttPublished: false,
    deviceReceived: false,
    codeValidated: false,
    uartFrameWritten: false,
    moduleAcknowledged: false,
    acResponse: 'unknown',
  };
}

function recentModuleAckPass(codeId: string, now: number): boolean {
  const oneDayMs = 24 * 60 * 60 * 1000;
  return getRecentCommands(50).some((c: any) => {
    const t = Number(c.acknowledged_at || c.created_at || 0);
    return c.action === 'ir_action'
      && c.ir_code_id === codeId
      && c.status === 'ir_executed'
      && c.failure_reason === 'ir_module_ack'
      && t > 0
      && now - t <= oneDayMs;
  });
}

function sendDeny(reply: FastifyReply, status: number, errorCode: string, message: string, requestId: string) {
  return reply.code(status).send({
    ok: false,
    errorCode,
    message,
    ...baseEnvelope(requestId),
  });
}

function buildDebugStatus(req: any, reply?: FastifyReply) {
  expireStaleIrDebugCommands();
  const now = Date.now();
  const expiresAtMs = parseDebugExpiresAt();
  const windowKey = debugWindowKey();
  const unlimited = debugCommandLimitUnlimited();
  const used = unlimited ? 0 : countIrDebugWindowCommands(windowKey);
  const remainingCommands = unlimited ? null : Math.max(0, debugMaxCommands() - used);
  const configured = debugWindowConfigured();
  const notExpired = debugNotExpired(now);
  const debugMode = configured && notExpired && (unlimited || (remainingCommands !== null && remainingCommands > 0));
  const latestDebug = getLatestIrDebugWindowCommand(windowKey);
  const cooldownUntil = latestDebug ? Number(latestDebug.created_at) + cooldownSeconds() * 1000 : 0;
  const cooldownRemainingSeconds = Math.max(0, Math.ceil((cooldownUntil - now) / 1000));
  const cooldownActive = cooldownSeconds() > 0 && cooldownRemainingSeconds > 0;

  const state = getDeviceState();
  const liveness = evaluateDeviceLiveness(state);
  const telemetry = getLatestTelemetry();
  const telemetryMetadataUsable = !!(
    telemetry
    && (telemetry.ir_code_id || telemetry.ir_code_length || telemetry.ir_code_sha256)
  );
  const legacyModuleAckPass = !telemetryMetadataUsable && recentModuleAckPass(expectedCodeId(), now);
  const irGateSource = telemetryMetadataUsable
    ? 'firmware_telemetry'
    : (legacyModuleAckPass ? 'recent_module_ack_legacy' : 'missing_firmware_metadata');
  const irReady = telemetryMetadataUsable
    ? (telemetry?.ir_ready === 1 || telemetry?.ir_ready === true)
    : legacyModuleAckPass;
  const codeIdMatch = telemetryMetadataUsable
    ? String(telemetry?.ir_code_id || '') === expectedCodeId()
    : legacyModuleAckPass;
  const codeLengthMatch = telemetryMetadataUsable
    ? Number(telemetry?.ir_code_length || 0) === expectedCodeLength()
    : legacyModuleAckPass;
  const codeShaMatch = telemetryMetadataUsable
    ? String(telemetry?.ir_code_sha256 || '').toLowerCase() === expectedCodeSha()
    : legacyModuleAckPass;
  const commandInFlight = countActiveIrCommands(now) > 0;
  const commandTtlSeconds = ttlSeconds();
  const csrfSession = reply && debugMode ? ensureDebugSession(req, reply) : null;

  const expiresAt = expiresAtMs ? new Date(expiresAtMs).toISOString() : null;
  const expiresInSeconds = expiresAtMs ? Math.max(0, Math.ceil((expiresAtMs - now) / 1000)) : null;
  const ir22hStructurePass = codeIdMatch && codeLengthMatch && codeShaMatch;
  const webRealIrEnabled = debugIrControlEnabled();
  const mqttBackendConnected = mqttConnected();

  return {
    ok: true,
    debugMode,
    debugWindowConfigured: configured,
    expiresAt,
    expiresInSeconds,
    remainingCommands,
    maxCommands: unlimited ? null : debugMaxCommands(),
    allowedCodeId: expectedCodeId(),
    codeLength: expectedCodeLength(),
    deviceOnline: liveness.online,
    deviceFresh: liveness.data_freshness === 'fresh',
    deviceFreshness: liveness.data_freshness,
    deviceLivenessReason: liveness.reason,
    mqttBackendConnected,
    webRealIrEnabled,
    irReady,
    telemetryMetadataUsable,
    legacyModuleAckPass,
    irGateSource,
    codeIdMatch,
    codeLengthMatch,
    codeShaMatch,
    ir22hStructurePass,
    commandInFlight,
    cooldownActive,
    cooldownRemainingSeconds,
    commandTtlSeconds,
    transmitEnabled: debugMode
      && webRealIrEnabled
      && mqttBackendConnected
      && liveness.online
      && liveness.data_freshness === 'fresh'
      && irReady
      && ir22hStructurePass
      && !commandInFlight
      && !cooldownActive
      && commandTtlSeconds <= 30,
    latestDebugCommand: latestDebug ? {
      commandId: latestDebug.command_id,
      status: latestDebug.status,
      mqttPublished: !!latestDebug.mqtt_published_at,
      deviceReceived: !!latestDebug.device_received_at,
      codeValidated: !!latestDebug.code_validated_at,
      uartFrameWritten: !!latestDebug.uart_written_at,
      moduleAcknowledged: !!latestDebug.module_ack_at,
      acResponse: 'unknown',
    } : null,
    csrfHeader: DEBUG_CSRF_HEADER,
    debugCsrf: csrfSession?.csrf,
  };
}

export async function registerIrDebugRoutes(fastify: FastifyInstance): Promise<void> {
  fastify.get('/api/ir/debug/status', async (req, reply) => {
    reply.send(buildDebugStatus(req, reply));
  });

  fastify.post('/api/ir/debug/transmit', { config: { rateLimit: false } }, async (req, reply) => {
    const requestId = cryptoRandomRequestId();
    const status = buildDebugStatus(req);

    if (!config.REAL_IR_DEBUG_MODE) return sendDeny(reply, 403, 'DEBUG_MODE_DISABLED', 'debug mode disabled', requestId);
    if (!debugNotExpired()) return sendDeny(reply, 403, 'DEBUG_WINDOW_EXPIRED', 'debug window expired', requestId);
    if (status.remainingCommands !== null && status.remainingCommands <= 0) return sendDeny(reply, 429, 'DEBUG_COMMAND_LIMIT_REACHED', 'debug command limit reached', requestId);
    if (!exactPublicOrigin(req)) return sendDeny(reply, 403, 'ORIGIN_DENIED', `origin must exactly match ${PUBLIC_ORIGIN}`, requestId);

    const session = validateDebugSession(req);
    if (!session.ok) return sendDeny(reply, 403, session.errorCode, session.message, requestId);

    if (!debugIrControlEnabled()) return sendDeny(reply, 403, 'WEB_REAL_IR_DISABLED', 'web real IR disabled', requestId);
    const parsed = transmitSchema.safeParse(req.body);
    if (!parsed.success) return sendDeny(reply, 400, 'INVALID_DEBUG_TRANSMIT_BODY', 'invalid debug transmit body', requestId);
    if (expectedCodeId() !== FIXED_CODE_ID) return sendDeny(reply, 403, 'DEBUG_CODE_CONFIG_INVALID', 'debug code config invalid', requestId);
    if (!mqttConnected()) return sendDeny(reply, 409, 'MQTT_BACKEND_OFFLINE', 'mqtt backend offline', requestId);
    if (!status.deviceOnline) return sendDeny(reply, 409, 'DEVICE_OFFLINE', 'device offline', requestId);
    if (!status.deviceFresh) return sendDeny(reply, 409, 'DEVICE_STALE', 'device state stale', requestId);
    if (!status.irReady) return sendDeny(reply, 409, 'IR_NOT_READY', 'firmware did not report IR ready', requestId);
    if (!status.codeIdMatch) return sendDeny(reply, 409, 'IR_CODE_ID_MISMATCH', 'firmware codeId mismatch', requestId);
    if (!status.codeLengthMatch) return sendDeny(reply, 409, 'IR_CODE_LENGTH_MISMATCH', 'firmware code length mismatch', requestId);
    if (!status.codeShaMatch) return sendDeny(reply, 409, 'IR_CODE_SHA_MISMATCH', 'firmware code sha mismatch', requestId);
    if (status.commandInFlight) return sendDeny(reply, 409, 'IR_COMMAND_IN_FLIGHT', 'another ir command is in flight', requestId);

    const idemHash = sha256Hex(parsed.data.idempotencyKey);
    if (getIrDebugCommandByIdempotencyHash(idemHash)) return sendDeny(reply, 409, 'IDEMPOTENCY_KEY_REPLAY', 'idempotency key already used', requestId);
    if (getCommand(parsed.data.commandId)) return sendDeny(reply, 409, 'COMMAND_ID_REPLAY', 'commandId already exists', requestId);
    if (status.cooldownActive) return sendDeny(reply, 429, 'DEBUG_COOLDOWN_ACTIVE', `debug cooldown active: ${status.cooldownRemainingSeconds}s`, requestId);
    if (ttlSeconds() > 30) return sendDeny(reply, 500, 'DEBUG_TTL_TOO_LONG', 'debug command ttl exceeds 30s', requestId);

    const dbIdempotencyKey = `debug:${idemHash}`;
    const res = dispatchIrAction(expectedCodeId(), {
      requested_by: 'anonymous-real-ir-debug',
      idempotency_key: dbIdempotencyKey,
      command_id: parsed.data.commandId,
      ttl_ms: ttlSeconds() * 1000,
      control_mode: 'debug',
      debug: {
        request_id: requestId,
        idempotency_key_hash: idemHash,
        debug_session_hash: session.sessionHash,
        debug_window_key: debugWindowKey(),
      },
    });

    if (res.offline_rejected) return sendDeny(reply, 409, 'DEVICE_OFFLINE', 'device offline', requestId);
    if (res.idempotency_replay) return sendDeny(reply, 409, 'IDEMPOTENCY_REPLAY', 'idempotency replay', requestId);

    insertEvent('ir_debug_command_created', config.DEVICE_ID, `command=${res.command_id} code=${expectedCodeId()}`);
    log.warn('anonymous real-ir debug command created', { requestId, command_id: res.command_id, code_id: expectedCodeId() });

    reply.send({
      ok: true,
      requestId,
      commandId: res.command_id,
      commandCreated: true,
      mqttPublished: !!res.mqtt_published,
      deviceReceived: false,
      codeValidated: false,
      uartFrameWritten: false,
      moduleAcknowledged: false,
      acResponse: 'unknown',
      status: res.status,
      allowedCodeId: expectedCodeId(),
      expiresAt: new Date(Date.now() + ttlSeconds() * 1000).toISOString(),
    });
  });
}

function cryptoRandomRequestId(): string {
  return 'req-' + sha256Hex(`${Date.now()}-${Math.random()}-${process.hrtime.bigint()}`).slice(0, 32);
}
