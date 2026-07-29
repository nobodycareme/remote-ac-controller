<script setup lang="ts">
/**
 * 统一内联 SVG 图标（无外部 CDN，替代 emoji）。
 * 线性风格，currentColor 继承文字颜色，stroke-width 1.8。
 */
import { computed } from 'vue';

const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 });

// 每个图标为一组 path/shape 的 d/attrs 描述（24x24 viewBox）
const ICONS: Record<string, string> = {
  // 导航
  home: '<path d="M4 11.5 12 4.5l8 7"/><path d="M6 10.5V19a1 1 0 0 0 1 1h3.5v-5h3v5H17a1 1 0 0 0 1-1v-8.5"/>',
  control: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  schedule: '<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/><path d="M3.5 9.5h17M8 3v4M16 3v4"/>',
  automation: '<path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3M6 6l2.1 2.1M15.9 15.9 18 18M18 6l-2.1 2.1M8.1 15.9 6 18"/><circle cx="12" cy="12" r="3.6"/>',
  chart: '<path d="M4 4v15.5a.5.5 0 0 0 .5.5H20"/><path d="M7.5 14.5l3.5-4 3 2.5 4.5-6"/>',
  settings: '<circle cx="12" cy="12" r="3.2"/><path d="M19.4 13.6a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V19.7a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H4.3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06A2 2 0 1 1 8.38 2.8l.06.06a1.7 1.7 0 0 0 1.87.34h.08a1.7 1.7 0 0 0 1.03-1.56V1.7"/>',
  // 模式
  snow: '<path d="M12 3v18M5 6.5l14 11M19 6.5l-14 11M12 3l-2 2.2M12 3l2 2.2M12 21l-2-2.2M12 21l2-2.2M5 6.5l2.9.5M5 17.5l2.9-.5M19 6.5l-2.9.5M19 17.5l-2.9-.5"/>',
  drop: '<path d="M12 3.5s6 6.4 6 10.6a6 6 0 0 1-12 0C6 9.9 12 3.5 12 3.5Z"/><path d="M9.5 14.2a2.6 2.6 0 0 0 2 2.4"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.4M12 19.1v2.4M2.5 12h2.4M19.1 12h2.4M4.9 4.9l1.7 1.7M17.4 17.4l1.7 1.7M19.1 4.9l-1.7 1.7M6.6 17.4l-1.7 1.7"/>',
  power: '<path d="M12 3.5v8"/><path d="M7 6.2a8 8 0 1 0 10 0"/>',
  // 天气
  'cloud-sun': '<circle cx="8" cy="8" r="3"/><path d="M8 2.5v1.6M2.5 8h1.6M4.2 4.2l1.1 1.1M11.8 4.2l-1.1 1.1"/><path d="M9 17.5h8.2a3.3 3.3 0 0 0 .4-6.6 5 5 0 0 0-9.4-1.2A3.8 3.8 0 0 0 9 17.5Z"/>',
  cloud: '<path d="M7 18h10.2a3.8 3.8 0 0 0 .5-7.6 5.5 5.5 0 0 0-10.6-1.4A4.2 4.2 0 0 0 7 18Z"/>',
  rain: '<path d="M7 15h10.2a3.8 3.8 0 0 0 .5-7.6A5.5 5.5 0 0 0 7.1 6 4.2 4.2 0 0 0 7 15Z"/><path d="M8.5 17.5 7.5 20M12.5 17.5l-1 2.5M16.5 17.5l-1 2.5"/>',
  snow2: '<path d="M7 15h10.2a3.8 3.8 0 0 0 .5-7.6A5.5 5.5 0 0 0 7.1 6 4.2 4.2 0 0 0 7 15Z"/><path d="M8 18.2h.01M12 19.5h.01M16 18.2h.01"/>',
  fog: '<path d="M4 9.5h16M6 13h12M8 16.5h8"/>',
  storm: '<path d="M7 14h10.2a3.8 3.8 0 0 0 .5-7.6A5.5 5.5 0 0 0 7.1 5 4.2 4.2 0 0 0 7 14Z"/><path d="m12.5 14-2 3.5h3L11.5 21"/>',
  wind: '<path d="M3.5 8h9a2.5 2.5 0 1 0-2.4-3.2M3.5 12h13.8a2.7 2.7 0 1 1-2.6 3.4M3.5 16h6.6a2.3 2.3 0 1 1-2.2 2.9"/>',
  // 通用
  thermometer: '<path d="M10 4a2 2 0 0 1 4 0v9.3a4.5 4.5 0 1 1-4 0Z"/><circle cx="12" cy="17" r="1.6"/>',
  humidity: '<path d="M12 3.5s6 6.4 6 10.6a6 6 0 0 1-12 0C6 9.9 12 3.5 12 3.5Z"/>',
  shield: '<path d="M12 3 5 6v5.2c0 4.4 3 8 7 9.8 4-1.8 7-5.4 7-9.8V6Z"/><path d="m9 11.8 2.2 2.2L15.5 9.5"/>',
  lock: '<rect x="5.5" y="10.5" width="13" height="9.5" rx="2"/><path d="M8.5 10.5V7.8a3.5 3.5 0 0 1 7 0v2.7"/>',
  plus: '<path d="M12 5.5v13M5.5 12h13"/>',
  trash: '<path d="M5 7h14M9.5 7V5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v2M7 7l1 12a1.5 1.5 0 0 0 1.5 1.4h5A1.5 1.5 0 0 0 16 19l1-12"/>',
  edit: '<path d="M14.5 5.5 18.5 9.5 9 19H5v-4Z"/><path d="m13 7 4 4"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  warning: '<path d="M12 4 2.8 19.5h18.4Z"/><path d="M12 10v4.2M12 16.8h.01"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  moon: '<path d="M20 13.5A8 8 0 0 1 10.5 4 8 8 0 1 0 20 13.5Z"/>',
  wifi: '<path d="M3 9.5a13.5 13.5 0 0 1 18 0M6 13a9 9 0 0 1 12 0M9 16.4a4.5 4.5 0 0 1 6 0"/><path d="M12 19.5h.01"/>',
  device: '<rect x="7" y="3.5" width="10" height="17" rx="2.2"/><path d="M11 18h2"/>',
  timeline: '<circle cx="6" cy="6" r="1.8"/><circle cx="6" cy="12" r="1.8"/><circle cx="6" cy="18" r="1.8"/><path d="M10.5 6H20M10.5 12H20M10.5 18H20"/>',
  remote: '<rect x="8" y="2.8" width="8" height="18.4" rx="2.4"/><circle cx="12" cy="7" r="1.4"/><path d="M10.3 11.4h3.4M10.3 14.4h3.4M10.3 17.4h3.4"/>',
};

const body = computed(() => ICONS[props.name] ?? ICONS.info);
</script>

<template>
  <svg
    class="app-icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    v-html="body"
  />
</template>
