// Task §十一/§十二/§十三 — weather is strictly DECOUPLED from device state.
// The WeatherService owns its own 10-minute refresh timer and SQLite cache; it never
// reads device telemetry, availability, MQTT, or last_seen. These tests prove the
// weather snapshot (and the /api/weather/current endpoint) is available even when the
// device is offline / has never reported, and that a failed live fetch preserves the
// last good snapshot instead of going blank.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import Fastify from 'fastify';
import cookie from '@fastify/cookie';
import { initDb, setWeatherCache } from '../src/db';
import { config } from '../src/config';
import { weatherService } from '../src/weather';
import { registerAuthRoutes } from '../src/routes/auth';
import { registerWeatherRoutes } from '../src/routes/weather';

const VALID_ORIGIN = (config.ALLOWED_ORIGINS || 'https://ac.example.com').split(',')[0].trim();

const SAMPLE_PAYLOAD = JSON.stringify({
  temperature_2m: 30.5,
  relative_humidity_2m: 55,
  apparent_temperature: 31.2,
  weather_code: 1,
  wind_speed_10m: 8,
  is_day: 1,
  time: '2026-07-22T10:00',
});

function seedCache(expiresAtOffsetMs: number) {
  const now = Date.now();
  setWeatherCache(config.WEATHER_CITY, SAMPLE_PAYLOAD, now, now, now + expiresAtOffsetMs);
}

async function buildApp() {
  const app = Fastify();
  await app.register(cookie);
  await registerAuthRoutes(app);
  await registerWeatherRoutes(app);
  return app;
}

beforeEach(async () => {
  await initDb();
  // No device telemetry/state row exists (simulates a device that is offline or has
  // never reported). The weather path must not depend on this being present.
});

afterEach(() => {
  weatherService.stop();
  vi.restoreAllMocks();
});

describe('Task §十一 — weather decoupled from device state', () => {
  it('getSnapshot returns the cached snapshot even with no device_state row', () => {
    seedCache(config.WEATHER_CACHE_MS); // fresh cache (10 min)
    weatherService.start();
    const snap = weatherService.getSnapshot();
    expect(snap).not.toBeNull();
    expect(snap!.temperature_2m).toBe(30.5);
    expect(snap!.city).toBe(config.WEATHER_CITY);
    expect(snap!.latitude).toBeCloseTo(34.34, 1);
    expect(snap!.longitude).toBeCloseTo(108.94, 1);
    weatherService.stop();
  });

  it('/api/weather/current returns 200 with the snapshot when the device is offline', async () => {
    // Network unavailable — proves the service does not depend on a live fetch to serve.
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network unavailable in test'));
    seedCache(config.WEATHER_CACHE_MS); // fresh → served from cache, no network needed
    weatherService.start();
    const app = await buildApp();
    const res = await app.inject({ method: 'GET', url: '/api/weather/current', headers: { origin: VALID_ORIGIN } });
    expect(res.statusCode).toBe(200);
    const body = res.json();
    expect(body.ok).toBe(true);
    expect(body.current.temperatureC).toBe(30.5);
    expect(body.location.name).toBe(config.WEATHER_CITY);
    expect(body.stale).toBe(false);
    await app.close();
    weatherService.stop();
  });

  it('on live-fetch failure the last-good snapshot is preserved and flagged stale (not blank)', async () => {
    // Expire the cache so the service actually attempts a fetch, which then fails.
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('open-meteo down'));
    seedCache(-1000); // already expired → refresh proceeds to fetch (which fails)
    weatherService.start();
    // Give the fire-and-forget refresh a moment to fail and record the error.
    await new Promise((r) => setTimeout(r, 60));
    const snap = weatherService.getSnapshot();
    expect(snap).not.toBeNull();
    expect(snap!.error).toContain('open-meteo down');
    expect(snap!.stale).toBe(true);
    expect(snap!.temperature_2m).toBe(30.5); // last good data retained
    weatherService.stop();
  });
});
