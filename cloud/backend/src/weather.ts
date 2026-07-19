import { config } from './config';
import { log } from './logger';
import { getWeatherCache, setWeatherCache } from './db';

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

const GEO_URL = 'https://geocoding-api.open-meteo.com/v1/search';
const FC_URL = 'https://api.open-meteo.com/v1/forecast';

// Confirm Xi'an via geocoding at startup (logs, does not block serving).
export async function confirmGeocoding(): Promise<void> {
  try {
    const url = `${GEO_URL}?name=${encodeURIComponent(config.WEATHER_CITY)}&count=1&language=zh&format=json&countryCode=CN`;
    const r = await fetch(url);
    if (!r.ok) { log.warn('geocoding non-ok', { status: r.status }); return; }
    const j = await r.json() as any;
    const hit = j?.results?.[0];
    if (!hit) { log.warn('geocoding no result'); return; }
    log.info('geocoding confirmed', {
      name: hit.name, country: hit.country, lat: hit.latitude, lon: hit.longitude,
      match: Math.abs(hit.latitude - config.WEATHER_LATITUDE) < 0.5 && Math.abs(hit.longitude - config.WEATHER_LONGITUDE) < 0.5,
    });
  } catch (e: any) {
    log.warn('geocoding failed', { err: e?.message });
  }
}

export async function fetchWeatherNow(): Promise<WeatherNow> {
  const cached = getWeatherCache(config.WEATHER_CITY) as any;
  const now = Date.now();
  const fresh = cached && now < cached.expires_at;
  const stale = cached && now < cached.expires_at + config.WEATHER_STALE_MS;

  if (fresh && cached) {
    const p = JSON.parse(cached.payload_json);
    return { ...p, fetched_at: cached.fetched_at, stale: false, source: 'open-meteo' };
  }

  try {
    const url = `${FC_URL}?latitude=${config.WEATHER_LATITUDE}&longitude=${config.WEATHER_LONGITUDE}` +
      `&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,is_day` +
      `&timezone=${encodeURIComponent(config.WEATHER_TIMEZONE)}`;
    const r = await fetch(url);
    if (!r.ok) throw new Error('open-meteo status ' + r.status);
    const j = await r.json() as any;
    const c = j.current;
    const payload: Omit<WeatherNow, 'fetched_at' | 'stale' | 'source'> = {
      temperature_2m: c.temperature_2m,
      relative_humidity_2m: c.relative_humidity_2m,
      apparent_temperature: c.apparent_temperature,
      weather_code: c.weather_code,
      wind_speed_10m: c.wind_speed_10m,
      is_day: c.is_day,
      time: c.time,
    };
    setWeatherCache(config.WEATHER_CITY, JSON.stringify(payload), now, now, now + config.WEATHER_CACHE_MS);
    return { ...payload, fetched_at: now, stale: false, source: 'open-meteo' };
  } catch (e: any) {
    log.warn('weather fetch failed', { err: e?.message });
    if (cached) {
      const p = JSON.parse(cached.payload_json);
      return { ...p, fetched_at: cached.fetched_at, stale: true, source: 'open-meteo-cache' };
    }
    throw e;
  }
}
