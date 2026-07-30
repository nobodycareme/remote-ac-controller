// Shared in-process event bus used to push device updates to WebSocket clients.
import { EventEmitter } from 'events';

export interface BusEvents {
  // telemetry row (with server_received_at)
  telemetry: Record<string, unknown>;
  // parsed state payload (if device publishes retained state)
  state: Record<string, unknown>;
  // availability payload { status: 'online'|'offline' }
  availability: Record<string, unknown>;
  // command ack { command_id, status, reason, ... }
  ack: Record<string, unknown>;
  // generic command lifecycle event { command_id, status }
  command: Record<string, unknown>;
}

export const bus = new EventEmitter();
bus.setMaxListeners(100);
