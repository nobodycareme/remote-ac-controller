import Fastify from 'fastify';
import cookie from '@fastify/cookie';
import rateLimit from '@fastify/rate-limit';
import websocket from '@fastify/websocket';
import staticPlugin from '@fastify/static';
import fs from 'fs';
import path from 'path';

import { config } from './config';
import { log } from './logger';
import { initDb, retentionCleanup, getDb } from './db';
import { getSession, startSessionCleanup } from './auth';
import { startMqttBridge } from './mqtt_bridge';
import { weatherService, confirmGeocoding } from './weather';
import { bus } from './bus';
import { requireOrigin } from './guards';

import { registerAuthRoutes } from './routes/auth';
import { registerDashboardRoutes } from './routes/dashboard';
import { registerDeviceRoutes } from './routes/device';
import { registerTelemetryRoutes } from './routes/telemetry';
import { registerWeatherRoutes } from './routes/weather';
import { registerAcRoutes } from './routes/ac';
import { registerEventsRoutes } from './routes/events';

// Allowed CORS origins (for browser fetches if served separately). Empty => same-origin only.
const ALLOWED_ORIGINS = (config.ALLOWED_ORIGINS || '')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);
const ALLOWED_ORIGIN_SET = new Set(ALLOWED_ORIGINS);

async function buildServer() {
  // Only trust reverse proxy from loopback (cloudflared runs on localhost)
  const fastify = Fastify({ logger: false, trustProxy: ['127.0.0.1', '::1'] });

  await fastify.register(cookie, { secret: config.SESSION_SECRET });
  await fastify.register(rateLimit, { max: 100, timeWindow: '1 minute', allowList: ['127.0.0.1', '::1'] });
  await fastify.register(websocket);

  // CORS for same-origin + configured origins (browser fetch from Tailscale domain).
  fastify.addHook('onRequest', (req, reply, done) => {
    const origin = req.headers.origin;
    if (origin && ALLOWED_ORIGIN_SET.has(origin)) {
      reply.header('access-control-allow-origin', origin);
      reply.header('access-control-allow-credentials', 'true');
      reply.header('access-control-allow-headers', 'content-type, x-csrf-token');
      reply.header('access-control-allow-methods', 'GET,POST,OPTIONS');
    }
    if (req.method === 'OPTIONS') {
      reply.code(204).send();
      return;
    }
    done();
  });

  // Health / Ready / Version
  fastify.get('/api/health', async () => ({ status: 'ok', uptime: process.uptime() }));
  fastify.get('/api/ready', async () => {
    try { getDb().prepare('SELECT 1').get(); return { status: 'ready', db: 'ok' }; }
    catch { return { status: 'not_ready', db: 'error' }; }
  });
  fastify.get('/api/version', async () => ({ version: '0.4.0', node: process.version }));

  // Routes (registered before static so /api wins).
  await registerAuthRoutes(fastify);
  await registerDashboardRoutes(fastify);
  await registerDeviceRoutes(fastify);
  await registerTelemetryRoutes(fastify);
  await registerWeatherRoutes(fastify);
  await registerAcRoutes(fastify);
  await registerEventsRoutes(fastify);

  // WebSocket: authenticated live updates with Origin validation.
  fastify.get('/api/ws', { websocket: true, preHandler: [requireOrigin] }, (connection: any, req: any) => {
    const socket = connection.socket;
    const sid = req.cookies?.sid;
    const session = sid ? getSession(sid) : null;
    if (!session) {
      socket.close(4001, 'unauthorized');
      return;
    }
    const send = (type: string, payload: unknown) => {
      try {
        socket.send(JSON.stringify({ type, payload, ts: Date.now() }));
      } catch {
        /* socket gone */
      }
    };
    const onTelemetry = (p: unknown) => send('telemetry', p);
    const onState = (p: unknown) => send('state', p);
    const onAvail = (p: unknown) => send('availability', p);
    const onAck = (p: unknown) => send('ack', p);
    const onCommand = (p: unknown) => send('command', p);
    const onWeather = (p: unknown) => send('weather_update', p);
    bus.on('telemetry', onTelemetry);
    bus.on('state', onState);
    bus.on('availability', onAvail);
    bus.on('ack', onAck);
    bus.on('command', onCommand);
    bus.on('weather_update', onWeather);
    send('hello', { device_id: config.DEVICE_ID });

    socket.on('close', () => {
      bus.off('telemetry', onTelemetry);
      bus.off('state', onState);
      bus.off('availability', onAvail);
      bus.off('ack', onAck);
      bus.off('command', onCommand);
      bus.off('weather_update', onWeather);
    });
  });

  // Serve frontend (if built). Non-/api unknown paths fall back to index.html (SPA).
  const distDir = path.resolve(__dirname, '../../frontend/dist');
  if (fs.existsSync(distDir)) {
    await fastify.register(staticPlugin, { root: distDir, prefix: '/', wildcard: true, index: ['index.html'] });
    fastify.setNotFoundHandler((req, reply) => {
      if (req.url.startsWith('/api/')) {
        reply.code(404).send({ error: 'not_found' });
        return;
      }
      reply.sendFile('index.html');
    });
  } else {
    fastify.setNotFoundHandler((req, reply) => {
      if (req.url.startsWith('/api/')) {
        reply.code(404).send({ error: 'not_found' });
        return;
      }
      reply.type('text/html').send('<h1>remote-ac-cloud backend</h1><p>Frontend not built. Run <code>npm run build</code> in frontend/.</p>');
    });
  }

  return fastify;
}

async function main() {
  initDb();

  startSessionCleanup();

  startMqttBridge();
  weatherService.start();
  confirmGeocoding().catch(() => {});

  // Retention cleanup hourly.
  setInterval(() => {
    try {
      retentionCleanup();
    } catch (e: any) {
      log.error('retention cleanup failed', { err: e?.message });
    }
  }, 3600_000);

  const app = await buildServer();
  const port = config.PORT;
  const host = config.HOST;
  try {
    await app.listen({ port, host });
    log.info('server listening', { port, host });
  } catch (e: any) {
    log.error('server start failed', { err: e?.message });
    process.exit(1);
  }

  const shutdown = () => {
    log.info('shutting down');
    try {
      getDb().close();
    } catch {
      /* ignore */
    }
    process.exit(0);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

main().catch((e) => {
  log.error('fatal', { err: e?.message });
  process.exit(1);
});
