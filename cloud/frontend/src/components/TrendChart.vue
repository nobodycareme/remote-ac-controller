<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick, computed } from 'vue';
import * as echarts from 'echarts';

const props = withDefaults(defineProps<{
  points: { t: number; temperature_c: number; humidity_pct: number }[];
  height?: number;
}>(), { height: 240 });

const el = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;

const hasData = computed(() => props.points.length > 0);

function themeColors(): { text: string; axis: string; temp: string; hum: string; tooltipBg: string; tooltipText: string } {
  const light = document.documentElement.getAttribute('data-theme') === 'light';
  return {
    text: light ? '#57687f' : '#9fb0cc',
    axis: light ? '#dde5f0' : '#283452',
    temp: light ? '#1a73e8' : '#4f9dff',
    hum: light ? '#0d9488' : '#36d399',
    tooltipBg: light ? '#ffffff' : '#222d47',
    tooltipText: light ? '#17213a' : '#eaf0fd',
  };
}

function render() {
  if (!chart || !hasData.value) return;
  const c = themeColors();
  const data = props.points.map((p) => [p.t, p.temperature_c, p.humidity_pct]);
  chart.setOption({
    grid: { left: 40, right: 40, top: 30, bottom: 30 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.tooltipBg,
      borderColor: c.axis,
      textStyle: { color: c.tooltipText, fontSize: 12 },
    },
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
      {
        name: '温度℃', type: 'line', smooth: true, showSymbol: false,
        data: data.map((d) => [d[0], d[1]]),
        lineStyle: { color: c.temp, width: 2.2 }, itemStyle: { color: c.temp },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: c.temp + '33' },
            { offset: 1, color: c.temp + '00' },
          ]),
        },
      },
      {
        name: '湿度%', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: false,
        data: data.map((d) => [d[0], d[2]]),
        lineStyle: { color: c.hum, width: 2 }, itemStyle: { color: c.hum },
      },
    ],
  });
}

function resize() {
  chart?.resize();
  render();
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

watch(() => props.points, async () => {
  await nextTick();
  render();
}, { deep: true });
defineExpose({ render });
</script>

<template>
  <div>
    <div v-show="hasData" ref="el" :style="{ width: '100%', height: height + 'px' }"></div>
    <div v-if="!hasData" class="chart-empty">暂无温湿度数据，稍候会自动刷新。</div>
  </div>
</template>
