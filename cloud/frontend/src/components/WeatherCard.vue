<script setup lang="ts">
/** 室外天气卡（独立 WeatherService 数据源，与设备状态解耦）。 */
import { computed } from 'vue';
import AppIcon from './AppIcon.vue';
import { weatherText, weatherIconName, formatTimestamp } from '../lib/format';

const props = defineProps<{
  weather: any | null;
  error: string | null;
}>();

const cur = computed(() => props.weather?.current ?? null);
const iconName = computed(() => (cur.value ? weatherIconName(cur.value.weatherCode) : 'cloud'));
</script>

<template>
  <div class="card" aria-label="室外天气">
    <h3><span class="card-title-icon"><AppIcon name="cloud-sun" :size="16" /></span>室外天气 · 西安</h3>
    <div v-if="cur" class="weather-card">
      <span class="weather-icon"><AppIcon :name="iconName" :size="44" /></span>
      <div>
        <div class="weather-temp">{{ cur.temperatureC.toFixed(1) }}<span style="font-size: 15px">℃</span></div>
        <div class="weather-desc">{{ weatherText(cur.weatherCode) }}<span v-if="weather?.stale" class="faint"> · 数据稍旧</span></div>
      </div>
      <div class="weather-metrics">
        <span class="sub"><AppIcon name="humidity" :size="12" /> {{ cur.relativeHumidity }}%</span>
        <span class="sub"><AppIcon name="wind" :size="12" /> {{ cur.windSpeed }} km/h</span>
        <span class="faint">{{ formatTimestamp(weather?.observedAt) }}</span>
      </div>
    </div>
    <div v-else-if="error" class="sub">{{ error }}</div>
    <div v-else class="sub">天气加载中…</div>
  </div>
</template>
