<script setup lang="ts">
/** 人类可读活动时间线（自动化执行记录 → 一句话文案）。 */
import { computed } from 'vue';
import AppIcon from './AppIcon.vue';
import { humanizeExecution, relativeTime, formatTimestamp, type ExecutionLike } from '../lib/format';

const props = withDefaults(defineProps<{
  executions: (ExecutionLike & { id: number })[];
  stateName: (id: string) => string;
  limit?: number;
  showAbsolute?: boolean;
}>(), { limit: 5, showAbsolute: false });

const items = computed(() =>
  props.executions.slice(0, props.limit).map((e) => {
    const h = humanizeExecution(e, props.stateName);
    return {
      id: e.id,
      title: h.title,
      ok: h.ok,
      icon: e.source === 'schedule' ? 'schedule' : 'automation',
      time: props.showAbsolute ? formatTimestamp(e.created_at) : relativeTime(e.created_at),
    };
  })
);
</script>

<template>
  <div class="timeline" role="list" aria-label="自动化活动记录">
    <div v-for="it in items" :key="it.id" class="tl-item" role="listitem">
      <span class="tl-badge" :class="it.ok ? 'ok' : 'bad'">
        <AppIcon :name="it.ok ? 'check' : 'warning'" :size="15" />
      </span>
      <div class="tl-body">
        <div class="tl-title">{{ it.title }}</div>
        <div class="tl-time">{{ it.time }}</div>
      </div>
    </div>
    <div v-if="items.length === 0" class="sub" style="padding: 6px 0">暂无自动化活动。</div>
  </div>
</template>
