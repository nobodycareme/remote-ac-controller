<script setup lang="ts">
/** 首页 Hero 气候卡：室温大数字 + 湿度 + 设备状态（人类可读）。 */
import { computed } from 'vue';
import AppIcon from './AppIcon.vue';
import { availabilityHuman, relativeTime, rssiHuman } from '../lib/format';

const props = defineProps<{
  temperature: number | null;
  humidity: number | null;
  availability: string | null | undefined;
  lastSeenAt: number | null | undefined;
  rssi: number | null | undefined;
}>();

const avail = computed(() => availabilityHuman(props.availability));
const availClass = computed(() => (avail.value.tone === 'ok' ? 'pill online' : avail.value.tone === 'bad' ? 'pill offline' : 'pill warn'));
const lastSeenText = computed(() => relativeTime(props.lastSeenAt ?? null));
const signalText = computed(() => rssiHuman(props.rssi));
</script>

<template>
  <section class="hero-card" aria-label="室内气候概览">
    <div class="hero-status">
      <span :class="availClass" role="status"><span class="dot" />{{ avail.text }}</span>
      <span class="faint" v-if="lastSeenAt">最后上报 {{ lastSeenText }}</span>
    </div>
    <div class="hero-main">
      <div>
        <div class="hero-temp-label"><AppIcon name="thermometer" :size="15" />室内温度</div>
        <div class="hero-temp">
          {{ temperature !== null ? temperature.toFixed(1) : '--' }}<span class="unit">℃</span>
        </div>
      </div>
      <div class="hero-side">
        <div class="hero-metric">
          <AppIcon name="humidity" :size="15" />湿度
          <strong>{{ humidity !== null ? humidity.toFixed(0) + '%' : '--' }}</strong>
        </div>
        <div class="hero-metric" v-if="rssi !== null && rssi !== undefined">
          <AppIcon name="wifi" :size="15" /><strong>{{ signalText }}</strong>
        </div>
      </div>
    </div>
    <div class="hero-foot">
      <slot name="foot" />
    </div>
  </section>
</template>
