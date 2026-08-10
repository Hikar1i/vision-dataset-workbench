<script setup lang="ts">
/** 等宽短标识：资源 ID、模式、来源、参数名。取代各页面自写的 <code> 样式。 */
withDefaults(defineProps<{ variant?: 'default' | 'id' }>(), { variant: 'default' })
</script>

<template>
  <span class="vdw-chip" :class="{ 'vdw-chip--id': variant === 'id' }"><slot /></span>
</template>

<style scoped>
.vdw-chip {
  display: inline-flex;
  align-items: center;
  /* 同 VTag：作为 grid 子元素不应被拉伸到整列宽 */
  width: fit-content;
  justify-self: start;
  height: 21px;
  padding: 0 7px;
  color: var(--vdw-ink-2);
  font: 400 13px/1 var(--vdw-mono);
  white-space: nowrap;
  background: var(--vdw-surface-2);
  border: 1px solid var(--vdw-line);
  border-radius: 3px;
}

.vdw-chip--id {
  color: var(--vdw-accent-ink);
  background: var(--vdw-accent-soft);
  border-color: #bfdde5;
}
</style>
