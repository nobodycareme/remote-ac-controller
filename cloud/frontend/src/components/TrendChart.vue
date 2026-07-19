<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import * as echarts from 'echarts';

const props = defineProps<{
  points: { t: number; temperature_c: number; humidity_pct: number }[];
}>();

const el = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;

function themeColors(): { text: string; axis: string; temp: string; hum: string } {
  const light = document.documentElement.getAttribute('data-theme') === 'light';
  return {
    text: light ? '#5b6b88' : '#9fb0cc',
    axis: light ? '#dbe3f0' : '#2a3650',
    temp: '#4f9dff',
    hum: '#36d399',
  };
}

function render() {
  if (!chart) return;
  const c = themeColors();
  const data = props.points.map((p) => [p.t, p.temperature_c, p.humidity_pct]);
  chart.setOption({
    grid: { left: 38, right: 38, top: 28, bottom: 28 },
    tooltip: { trigger: 'axis' },
    legend: { data: ['温度℃', '湿度%'], textStyle: { color: c.text }, top: 0, right: 0 },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: c.axis } },
      axisLabel: { color: c.text, hideOverlap: true },
    },
    yAxis: [
      { type: 'value', name: '℃', min: 0, max: 50, axisLabel: { color: c.text }, splitLine: { lineStyle: { color: c.axis } } },
      { type: 'value', name: '%', min: 0, max: 100, axisLabel: { color: c.text }, splitLine: { show: false } },
    ],
    series: [
      { name: '温度℃', type: 'line', smooth: true, showSymbol: false, data: data.map((d) => [d[0], d[1]]), lineStyle: { color: c.temp, width: 2 }, itemStyle: { color: c.temp } },
      { name: '湿度%', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: false, data: data.map((d) => [d[0], d[2]]), lineStyle: { color: c.hum, width: 2 }, itemStyle: { color: c.hum } },
    ],
  });
}

function resize() {
  chart?.resize();
}

onMounted(async () => {
  await nextTick();
  if (el.value) {
    chart = echarts.init(el.value);
    render();
    window.addEventListener('resize', resize);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize);
  chart?.dispose();
});

watch(() => props.points, render, { deep: true });
defineExpose({ render });
</script>

<template>
  <div ref="el" style="width: 100%; height: 220px"></div>
</template>
