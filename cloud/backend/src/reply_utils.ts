import { FastifyReply } from 'fastify';
import { v4 as uuid } from 'uuid';

export interface DenyOptions {
  ir_control?: 'armed' | 'disabled';
  commandCreated?: boolean;
  mqttPublished?: boolean;
  deviceReceived?: boolean;
  irTransmitted?: boolean;
  [key: string]: unknown;
}

/**
 * Structured rejection envelope (Task §八). Every deny path returns the same shape
 * so the frontend can show a precise stage instead of a bare "403".
 *
 *   { ok, errorCode, message, requestId, commandCreated, mqttPublished,
 *     deviceReceived, irTransmitted, ...extra }
 */
export function deny(reply: FastifyReply, status: number, errorCode: string, message: string, extra: DenyOptions = {}): FastifyReply {
  const { ir_control, commandCreated, mqttPublished, deviceReceived, irTransmitted, ...rest } = extra;
  return reply.code(status).send({
    ok: false,
    errorCode,
    message,
    requestId: uuid(),
    commandCreated: commandCreated ?? false,
    mqttPublished: mqttPublished ?? false,
    deviceReceived: deviceReceived ?? false,
    irTransmitted: irTransmitted ?? false,
    ...(ir_control ? { ir_control } : {}),
    ...rest,
  });
}
