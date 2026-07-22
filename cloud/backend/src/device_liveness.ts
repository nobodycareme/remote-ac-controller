// Shared, trusted device-liveness evaluator (Section 五/六 false-online fix).
//
// Root cause of the previous bug: the backend treated the retained MQTT
// `availability=online` message as proof of realtime presence and refreshed
// `last_seen_at` on every receipt. After a broker/backend restart the broker
// REPLAYS the retained online message, which made a dead/offline device look
// online forever (command interface accepted commands it could never receive).
//
// Fix: `last_seen_at` is advanced ONLY by REAL activity (telemetry / state / ack),
// never by an availability message (see db.ts COALESCE + mqtt_bridge.handleMessage).
// This module is the SINGLE source of truth for "is the device actually online"
// and MUST be used by BOTH the command dispatcher (offline gate) and the
// dashboard endpoint. Keeping them on one function guarantees they can never
// disagree.
import { config } from './config';

export type Freshness = 'fresh' | 'stale' | 'unknown';

export interface DeviceLiveness {
  /** Trusted realtime presence — drives the command offline-gate. */
  online: boolean;
  /** Raw availability hint from the availability topic (online/offline/unknown). */
  availability_hint: string;
  /** Last time the backend observed REAL activity (telemetry/state/ack). */
  last_seen_at: number | null;
  /** Last time fresh telemetry arrived. */
  last_telemetry_at: number | null;
  /** Telemetry recency for UI badges. */
  data_freshness: Freshness;
  /** Human-readable diagnostic reason (for logs / debugging). */
  reason: string;
}

/**
 * Evaluate trusted device liveness from the persisted device_state row.
 *
 * Decision rules:
 *  - No row at all => offline / unknown.
 *  - availability === 'offline' (LWT) is AUTHORITATIVE: device is dead regardless
 *    of any stale last_seen_at. This prevents a retained offline message from
 *    leaving the device falsely online.
 *  - Otherwise, trusted presence is driven ONLY by `last_seen_at` freshness
 *    (real activity). A retained `availability=online` replayed at startup never
 *    advances last_seen_at, so it CANNOT fake presence here.
 */
export function evaluateDeviceLiveness(state: any | null): DeviceLiveness {
  if (!state) {
    return {
      online: false,
      availability_hint: 'unknown',
      last_seen_at: null,
      last_telemetry_at: null,
      data_freshness: 'unknown',
      reason: 'no_state',
    };
  }

  const availabilityHint: string = state.availability ?? 'unknown';
  const lastSeenAt: number | null = state.last_seen_at ?? null;
  const lastTelemetryAt: number | null = state.last_telemetry_at ?? null;
  const now = Date.now();

  // LWT offline is authoritative — device is dead, no matter what last_seen says.
  if (availabilityHint === 'offline') {
    return {
      online: false,
      availability_hint: 'offline',
      last_seen_at: lastSeenAt,
      last_telemetry_at: lastTelemetryAt,
      data_freshness: 'stale',
      reason: 'availability_offline_lwt',
    };
  }

  // Trusted presence is driven by REAL activity (last_seen_at), NOT the hint.
  const ageLastSeen = lastSeenAt == null ? Infinity : now - lastSeenAt;
  const online = ageLastSeen <= config.OFFLINE_THRESHOLD_MS;

  // Telemetry recency badge.
  const ageTelemetry = lastTelemetryAt == null ? Infinity : now - lastTelemetryAt;
  let dataFreshness: Freshness;
  if (!online) {
    dataFreshness = 'unknown';
  } else if (ageTelemetry <= config.STALE_THRESHOLD_MS) {
    dataFreshness = 'fresh';
  } else {
    dataFreshness = 'stale';
  }

  return {
    online,
    availability_hint: availabilityHint,
    last_seen_at: lastSeenAt,
    last_telemetry_at: lastTelemetryAt,
    data_freshness: dataFreshness,
    reason: online ? 'last_seen_recent' : 'last_seen_stale',
  };
}
