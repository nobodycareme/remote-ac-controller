// Structured logger. Never logs secrets: cookie, password, session id, authorization.
const SENSITIVE = new Set(['password', 'session', 'sessionid', 'cookie', 'authorization', 'set-cookie', 'mqttpassword', 'token', 'csrf']);

function redact(value: unknown, depth = 0): unknown {
  if (value === null || value === undefined) return value;
  if (typeof value !== 'object') return value;
  if (Array.isArray(value)) return depth > 3 ? '[array]' : value.map((v) => redact(v, depth + 1));
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    const key = k.toLowerCase();
    if (SENSITIVE.has(key) || key.includes('password') || key.includes('secret') || key.includes('cookie') || key.includes('token')) {
      out[k] = '[redacted]';
    } else {
      out[k] = redact(v, depth + 1);
    }
  }
  return out;
}

function emit(level: string, msg: string, meta?: unknown) {
  const entry = { ts: new Date().toISOString(), level, msg, ...(meta !== undefined ? { meta: redact(meta) } : {}) };
  const line = JSON.stringify(entry);
  if (level === 'error') console.error(line);
  else console.log(line);
}

export const log = {
  info: (msg: string, meta?: unknown) => emit('info', msg, meta),
  warn: (msg: string, meta?: unknown) => emit('warn', msg, meta),
  error: (msg: string, meta?: unknown) => emit('error', msg, meta),
};
