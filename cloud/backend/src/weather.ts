import { config } from './config';
import { log } from './logger';
import { getWeatherCache, setWeatherCache } from './db';
import { bus } from './bus';

export interface WeatherNow {
  temperature_2m: number;
  relative_humidity_2m: number;
  apparent_temperature: number;
  weather_code: number;
  wind_speed_10m: number;
  is_day: number;
  time: string; // observation time (API)
  fetched_at: number; // server fetch time
  stale: boolean;
  source: string;
}

// Full snapshot served to clients. ALL fields are computed by the service itself —
// never from device telemetry, availability, or MQTT state.
export interface WeatherSnapshot extends WeatherNow {
  city: string;
  latitude: number;
  longitude: number;
  timezone: string;
  observed_at: number;
  last_success_at: number;
  next_refresh_at: number;
  error: string | null;
}

const GEO_URL = 'https://geocoding-api.open-meteo.com/v1/search';
const FC_URL = 'https://api.open-meteo.com/v1/forecast';

// Confirm Xi'an via geocoding at startup (logs, does not block serving).
export async function confirmGeocoding(): Promise<void> {
  try {
    const url = `${GEO_URL}?name=${encodeURIComponent(config.WEATHER_CITY)}&count=1&language=zh&format=json&countryCode=CN`;
    const r = await fetch(url);
    if (!r.ok) {
      log.warn('geocoding non-ok', { status: r.status });
      return;
    }
    const j = (await r.json()) as any;
    const hit = j?.results?.[0];
    if (!hit) {
      log.warn('geocoding no result');
      return;
    }
    log.info('geocoding confirmed', {
      name: hit.name,
      country: hit.country,
      lat: hit.latitude,
      lon: hit.longitude,
      match: Math.abs(hit.latitude - config.WEATHER_LATITUDE) < 0.5 && Math.abs(hit.longitude - config.WEATHER_LONGITUDE) < 0.5,
    });
  } catch (e: any) {
    log.warn('geocoding failed', { err: e?.message });
  }
}

function snapshotFromCacheRow(cached: any): WeatherSnapshot | null {
  if (!cached) return null;
  const p = JSON.parse(cached.payload_json);
  const now = Date.now();
  const stale = now > cached.expires_at + config.WEATHER_STALE_MS;
  return {
    ...p,
    city: config.WEATHER_CITY,
    latitude: config.WEATHER_LATITUDE,
    longitude: config.WEATHER_LONGITUDE,
    timezone: config.WEATHER_TIMEZONE,
    observed_at: cached.observed_at,
    fetched_at: cached.fetched_at,
    last_success_at: cached.fetched_at,
    next_refresh_at: cached.expires_at,
    stale,
    error: null,
  };
}

/**
 * WeatherService — fully independent of the device.
 *
 * Lifecycle (see Task §十一/§十二/§十三):
 *   process start → load last cache (if any) → immediate fetch → independent
 *   10-minute timer → persist success to SQLite → emit bus 'weather_update'.
 *
 * It NEVER reads device.online / lastSeen / MQTT / DHT. Device state cannot
 * pause, stop, or clear the weather timer or its cache.
 */
class WeatherService {
  private timer: ReturnType<typeof setInterval> | null = null;
  private snapshot: WeatherSnapshot | null = null;
  private inFlight = false;

  start(): void {
    // Hydrate from the last successful cache immediately so /api/weather/current
    // returns data even before the first live fetch completes (and across restarts).
    this.snapshot = snapshotFromCacheRow(getWeatherCache(config.WEATHER_CITY));
    // Clear any prior timer before (re)starting to avoid leaked/duplicate intervals.
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
    // Kick an immediate refresh (fire-and-forget; does not block startup).
    this.refresh().catch(() => {});
    this.timer = setInterval(() => {
      this.refresh().catch(() => {});
    }, config.WEATHER_REFRESH_MS).unref();
    log.info('weather service started', { refresh_ms: config.WEATHER_REFRESH_MS });
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  getSnapshot(): WeatherSnapshot | null {
    return this.snapshot;
  }

  async refresh(): Promise<void> {
    if (this.inFlight) return; // collapse concurrent refreshes
    this.inFlight = true;
    try {
      const w = await this.fetchOnce();
      const changed = !this.snapshot || this.snapshot.fetched_at !== w.fetched_at;
      this.snapshot = w;
      if (changed) bus.emit('weather_update', w); // push to WS clients
    } catch (e: any) {
      const msg = e?.message ?? 'fetch_failed';
      if (this.snapshot) {
        // Keep showing last good data; merely flag it stale + record error.
        this.snapshot = { ...this.snapshot, error: msg, stale: true };
      } else {
        // No cache at all: try to load cache one more time as a fallback.
        this.snapshot = snapshotFromCacheRow(getWeatherCache(config.WEATHER_CITY));
        if (this.snapshot) this.snapshot = { ...this.snapshot, error: msg };
      }
      log.warn('weather refresh failed', { err: msg });
    } finally {
      this.inFlight = false;
    }
  }

  private async fetchOnce(): Promise<WeatherSnapshot> {
    const cached = getWeatherCache(config.WEATHER_CITY) as any;
    const now = Date.now();
    const fresh = cached && now < cached.expires_at;
    if (fresh) {
      const snap = snapshotFromCacheRow(cached);
      if (snap) return snap;
    }

    const url =
      `${FC_URL}?latitude=${config.WEATHER_LATITUDE}&longitude=${config.WEATHER_LONGITUDE}` +
      `&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,is_day` +
      `&timezone=${encodeURIComponent(config.WEATHER_TIMEZONE)}`;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    let res: Response;
    try {
      res = await fetch(url, { signal: controller.signal });
    } finally {
      clearTimeout(timeout);
    }
    if (!res.ok) throw new Error('open-meteo status ' + res.status);
    const j = (await res.json()) as any;
    const c = j.current;
    const payload = {
      temperature_2m: c.temperature_2m,
      relative_humidity_2m: c.relative_humidity_2m,
      apparent_temperature: c.apparent_temperature,
      weather_code: c.weather_code,
      wind_speed_10m: c.wind_speed_10m,
      is_day: c.is_day,
      time: c.time,
    };
    const fetched_at = Date.now();
    setWeatherCache(config.WEATHER_CITY, JSON.stringify(payload), fetched_at, fetched_at, fetched_at + config.WEATHER_CACHE_MS);
    return {
      ...payload,
      city: config.WEATHER_CITY,
      latitude: config.WEATHER_LATITUDE,
      longitude: config.WEATHER_LONGITUDE,
      timezone: config.WEATHER_TIMEZONE,
      observed_at: fetched_at,
      fetched_at,
      last_success_at: fetched_at,
      next_refresh_at: fetched_at + config.WEATHER_REFRESH_MS,
      stale: false,
      error: null,
      source: 'open-meteo',
    };
  }
}

export const weatherService = new WeatherService();
