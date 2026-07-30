<script setup lang="ts">
/**
 * 首页 Hero 气候卡（OverviewGrid 子项，与 WeatherCard 同级等高）。
 * 内部三区：状态行 / 主数据+辅助指标 / 底部自动化提示。
 * 指标区使用 auto-fit Grid 填充宽度，避免宽屏中间大量空白。
 */
import { computed } from 'vue';
import AppIcon from './AppIcon.vue';
import { availabilityHuman, relativeTime, rssiHuman } from '../lib/format';

const props = defineProps<{
  temperature: number | null;
  humidity: number | null;
  availability: string | null | undefined;
  lastSeenAt: number | null | undefined;
  rssi: number | null | undefined;
  /** 最近一次发送的空调状态描述（如"制冷 26℃ 自动风"），无法确认时不显示 */
  lastSent?: string | null;
}>();

const avail = computed(() => availabilityHuman(props.availability));
const availClass = computed(() => (avail.value.tone === 'ok' ? 'pill online' : avail.value.tone === 'bad' ? 'pill offline' : 'pill warn'));
const lastSeenText = computed(() => relativeTime(props.lastSeenAt ?? null));
const signalText = computed(() => rssiHuman(props.rssi));
</script>

<template>
  <section class="hero-card ov-hero" aria-label="室内气候概览">
    <div class="hero-status">
      <span :class="availClass" role="status"><span class="dot" />设备{{ avail.text }}</span>
      <span class="faint" v-if="lastSeenAt">最后上报 {{ lastSeenText }}</span>
    </div>
    <div class="hero-body">
      <div class="hero-primary">
        <div class="hero-temp-label"><AppIcon name="thermometer" :size="15" />室内温度</div>
        <div class="hero-temp">
          {{ temperature !== null ? temperature.toFixed(1) : '--' }}<span class="unit">℃</span>
        </div>
      </div>
      <div class="hero-metrics">
        <div class="hero-metric">
          <span class="hm-label"><AppIcon name="humidity" :size="13" />室内湿度</span>
          <strong>{{ humidity !== null ? humidity.toFixed(0) + '%' : '--' }}</strong>
        </div>
        <div class="hero-metric" v-if="rssi !== null && rssi !== undefined">
          <span class="hm-label"><AppIcon name="wifi" :size="13" />信号</span>
          <strong>{{ signalText }}</strong>
        </div>
        <div class="hero-metric" v-if="lastSent">
          <span class="hm-label"><AppIcon name="remote" :size="13" />最近发送</span>
          <strong>{{ lastSent }}</strong>
        </div>
      </div>
    </div>
    <div class="hero-foot">
      <slot name="foot" />
    </div>
  </section>
</template>
