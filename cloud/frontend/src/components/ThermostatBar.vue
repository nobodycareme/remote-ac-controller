<script setup lang="ts">
/** 恒温器可视化阈值条：20–34℃ 范围内标出关机阈值、开机阈值与当前室温。 */
import { computed } from 'vue';

const props = defineProps<{
  onThreshold: number;
  offThreshold: number;
  currentTemp: number | null;
}>();

const MIN = 20;
const MAX = 34;

function pct(v: number): number {
  return Math.min(100, Math.max(0, ((v - MIN) / (MAX - MIN)) * 100));
}

const onPct = computed(() => pct(props.onThreshold));
const offPct = computed(() => pct(props.offThreshold));
const curPct = computed(() => (props.currentTemp === null ? null : pct(props.currentTemp)));
</script>

<template>
  <div class="thermo-bar-wrap" role="img" :aria-label="`温控区间：室温高于 ${onThreshold}℃ 自动开机，低于 ${offThreshold}℃ 自动关机` + (currentTemp !== null ? `，当前室温 ${currentTemp.toFixed(1)}℃` : '')">
    <div class="thermo-bar">
      <span class="thermo-marker mk-off" :style="{ left: offPct + '%' }" />
      <span class="thermo-marker mk-on" :style="{ left: onPct + '%' }" />
      <span v-if="curPct !== null" class="thermo-current" :style="{ left: curPct + '%' }" />
    </div>
    <div class="thermo-labels"><span>20℃</span><span>27℃</span><span>34℃</span></div>
    <div class="thermo-legend">
      <span class="tl"><span class="tl-dot" style="background: var(--danger)" />≥ {{ onThreshold }}℃ 自动开机</span>
      <span class="tl"><span class="tl-dot" style="background: var(--ok)" />≤ {{ offThreshold }}℃ 自动关机</span>
      <span class="tl" v-if="currentTemp !== null"><span class="tl-dot" style="background: var(--text); border: 1px solid var(--border-strong)" />当前 {{ currentTemp.toFixed(1) }}℃</span>
    </div>
  </div>
</template>
