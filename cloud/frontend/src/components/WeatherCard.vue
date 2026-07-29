<script setup lang="ts">
/**
 * 室外天气卡（OverviewGrid 子项，与 ClimateHero 同级等高）。
 * 卡片为 flex 纵向布局：标题 / 主体（图标+温度+指标）/ 底部更新时间贴底。
 */
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
  <div class="card weather-card-root ov-weather" aria-label="室外天气">
    <h3><span class="card-title-icon"><AppIcon name="cloud-sun" :size="16" /></span>室外天气 · 西安</h3>
    <template v-if="cur">
      <div class="weather-body">
        <span class="weather-icon"><AppIcon :name="iconName" :size="44" /></span>
        <div class="weather-main">
          <div class="weather-temp">{{ cur.temperatureC.toFixed(1) }}<span style="font-size: 15px">℃</span></div>
          <div class="weather-desc">{{ weatherText(cur.weatherCode) }}<span v-if="weather?.stale" class="faint"> · 数据稍旧</span></div>
        </div>
        <div class="weather-metrics">
          <span class="sub"><AppIcon name="humidity" :size="12" /> 湿度 {{ cur.relativeHumidity }}%</span>
          <span class="sub"><AppIcon name="wind" :size="12" /> 风速 {{ cur.windSpeed }} km/h</span>
        </div>
      </div>
      <div class="weather-foot">更新于 {{ formatTimestamp(weather?.observedAt) }}</div>
    </template>
    <div v-else-if="error" class="sub weather-body">{{ error }}</div>
    <div v-else class="sub weather-body">天气加载中…</div>
  </div>
</template>
