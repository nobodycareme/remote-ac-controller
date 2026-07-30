import crypto from 'node:crypto';
import { FastifyReply, FastifyRequest } from 'fastify';
import { v4 as uuid } from 'uuid';
import { config } from './config';
import {
  deleteExpiredIrDebugSessions,
  getIrDebugSession,
  touchIrDebugSession,
  upsertIrDebugSession,
} from './db';

export const DEBUG_COOKIE = 'ir_debug_sid';
export const DEBUG_CSRF_HEADER = 'x-ir-debug-csrf';

export function sha256Hex(value: string): string {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function randomToken(): string {
  return uuid() + '-' + crypto.randomBytes(16).toString('hex');
}

function timingSafeHexEqual(a: string, b: string): boolean {
  try {
    return crypto.timingSafeEqual(Buffer.from(a, 'hex'), Buffer.from(b, 'hex'));
  } catch {
    return false;
  }
}

export function parseDebugExpiresAt(): number | null {
  const raw = String(config.REAL_IR_DEBUG_EXPIRES_AT || '').trim();
  if (!raw) return null;
  if (/^\d+$/.test(raw)) {
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) return null;
    return n > 4_000_000_000 ? n : n * 1000;
  }
  const t = Date.parse(raw);
  return Number.isFinite(t) ? t : null;
}

export function debugWindowKey(): string {
  const expiresAt = parseDebugExpiresAt() ?? 0;
  return sha256Hex([
    expiresAt,
    config.REAL_IR_DEBUG_ALLOWED_CODE_ID,
    config.REAL_IR_DEBUG_ALLOWED_CODE_SHA256.toLowerCase(),
    config.REAL_IR_DEBUG_ALLOWED_CODE_LENGTH,
  ].join('|'));
}

export function debugWindowConfigured(): boolean {
  return !!config.REAL_IR_DEBUG_MODE;
}

export function debugNotExpired(now = Date.now()): boolean {
  const expiresAt = parseDebugExpiresAt();
  return expiresAt === null || now < expiresAt;
}

function requestUserAgentHash(req: FastifyRequest): string {
  const ua = Array.isArray(req.headers['user-agent'])
    ? req.headers['user-agent'][0]
    : req.headers['user-agent'] ?? '';
  return sha256Hex(String(ua));
}

export interface DebugSessionResult {
  sessionHash: string;
  csrf: string;
  expiresAt: number;
}

export function ensureDebugSession(req: FastifyRequest, reply: FastifyReply): DebugSessionResult | null {
  const expiresAt = parseDebugExpiresAt();
  const now = Date.now();
  if (!config.REAL_IR_DEBUG_MODE || !debugNotExpired(now)) return null;
  deleteExpiredIrDebugSessions(now);

  const windowKey = debugWindowKey();
  const userAgentHash = requestUserAgentHash(req);
  const rawCookie = req.cookies?.[DEBUG_COOKIE];
  const existingHash = rawCookie ? sha256Hex(String(rawCookie)) : '';
  const existing = existingHash ? getIrDebugSession(existingHash) : null;
  const csrf = randomToken();
  const csrfHash = sha256Hex(csrf);
  const sessionTtlMs = Math.max(1, Number(config.REAL_IR_DEBUG_SESSION_TTL_SECONDS || 3600) * 1000);
  const sessionExpiresAt = expiresAt ? Math.min(now + sessionTtlMs, expiresAt) : now + sessionTtlMs;

  if (
    existing &&
    existing.expires_at > now &&
    existing.window_key === windowKey &&
    existing.user_agent_hash === userAgentHash
  ) {
    upsertIrDebugSession({
      sid_hash: existingHash,
      csrf_hash: csrfHash,
      user_agent_hash: userAgentHash,
      window_key: windowKey,
      created_at: existing.created_at,
      expires_at: sessionExpiresAt,
      last_access: now,
    });
    return { sessionHash: existingHash, csrf, expiresAt: sessionExpiresAt };
  }

  const sessionId = randomToken();
  const sidHash = sha256Hex(sessionId);
  upsertIrDebugSession({
    sid_hash: sidHash,
    csrf_hash: csrfHash,
    user_agent_hash: userAgentHash,
    window_key: windowKey,
    created_at: now,
    expires_at: sessionExpiresAt,
    last_access: now,
  });
  reply.setCookie(DEBUG_COOKIE, sessionId, {
    httpOnly: true,
    sameSite: 'strict',
    path: '/api/ir/debug',
    secure: process.env.NODE_ENV === 'production' || config.PUBLIC_BASE_URL.startsWith('https://'),
    maxAge: Math.max(1, Math.floor((sessionExpiresAt - now) / 1000)),
  });
  return { sessionHash: sidHash, csrf, expiresAt: sessionExpiresAt };
}

export function validateDebugSession(req: FastifyRequest): { ok: true; sessionHash: string } | { ok: false; errorCode: string; message: string } {
  const now = Date.now();
  if (!config.REAL_IR_DEBUG_MODE || !debugNotExpired(now)) {
    return { ok: false, errorCode: 'DEBUG_WINDOW_CLOSED', message: '未发送：临时调试窗口未开启或已过期' };
  }
  deleteExpiredIrDebugSessions(now);
  const sid = req.cookies?.[DEBUG_COOKIE];
  if (!sid) {
    return { ok: false, errorCode: 'DEBUG_SESSION_REQUIRED', message: '未发送：匿名调试会话缺失，请重新打开页面' };
  }
  const sidHash = sha256Hex(String(sid));
  const row = getIrDebugSession(sidHash);
  if (!row || row.expires_at <= now || row.window_key !== debugWindowKey()) {
    return { ok: false, errorCode: 'DEBUG_SESSION_EXPIRED', message: '未发送：匿名调试会话已失效，请重新打开页面' };
  }
  if (row.user_agent_hash !== requestUserAgentHash(req)) {
    return { ok: false, errorCode: 'DEBUG_SESSION_BROWSER_MISMATCH', message: '未发送：匿名调试会话与当前浏览器不匹配' };
  }
  const header = req.headers[DEBUG_CSRF_HEADER];
  const token = Array.isArray(header) ? header[0] : header;
  if (!token || !timingSafeHexEqual(String(row.csrf_hash), sha256Hex(String(token)))) {
    return { ok: false, errorCode: 'DEBUG_CSRF_INVALID', message: '未发送：匿名调试 CSRF 校验失败' };
  }
  touchIrDebugSession(sidHash, now);
  return { ok: true, sessionHash: sidHash };
}
