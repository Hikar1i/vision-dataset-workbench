<script setup lang="ts">
import { computed } from 'vue'

import { splitDateTime } from './dateTime'

const props = defineProps<{ value: string | null | undefined }>()
const parts = computed(() => splitDateTime(props.value))
</script>

<template>
  <time class="vdw-date-time" :datetime="value || undefined">
    <span class="vdw-date-time__date">{{ parts.date }}</span>
    <span v-if="parts.time" class="vdw-date-time__time">{{ parts.time }}</span>
  </time>
</template>

<style scoped>
.vdw-date-time {
  display: inline-grid;
  gap: 2px;
  color: var(--vdw-ink-2);
  font: 500 13px/1.3 var(--vdw-mono);
  white-space: nowrap;
}

.vdw-date-time > span {
  display: block;
}

.vdw-date-time__time {
  color: var(--vdw-ink-3);
}
</style>
