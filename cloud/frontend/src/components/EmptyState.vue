<script setup lang="ts">
/** 通用空状态：图标 + 标题 + 描述 + 可选操作按钮。 */
import AppIcon from './AppIcon.vue';

defineProps<{
  icon: string;
  title: string;
  desc?: string;
  actionText?: string;
}>();

const emit = defineEmits<{ (e: 'action'): void }>();
</script>

<template>
  <div class="empty-state">
    <span class="es-icon"><AppIcon :name="icon" :size="44" /></span>
    <div class="es-title">{{ title }}</div>
    <div class="es-desc" v-if="desc">{{ desc }}</div>
    <button v-if="actionText" @click="emit('action')">{{ actionText }}</button>
  </div>
</template>
