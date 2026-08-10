<script setup lang="ts">
/** 进度条。颜色跟随状态语气，保证"完成"永远是绿、"异常"永远是红。 */
import { computed } from 'vue'
import { TONE_COLOR, type Tone } from './status'

const props = withDefaults(defineProps<{
  value: number
  tone?: Tone
  label?: string
}>(), { tone: 'run' })

const width = computed(() => `${Math.min(100, Math.max(0, props.value))}%`)
</script>

<template>
  <div
    class="vdw-bar"
    role="progressbar"
    :aria-valuenow="Math.round(value)"
    aria-valuemin="0"
    aria-valuemax="100"
    :aria-label="label"
  >
    <i :style="{ width, background: TONE_COLOR[tone] }" />
  </div>
</template>

<style scoped>
.vdw-bar {
  height: 4px;
  overflow: hidden;
  background: var(--vdw-surface-3);
  border-radius: 2px;
}

.vdw-bar i {
  display: block;
  height: 100%;
  border-radius: 2px;
  transition: width var(--vdw-motion-base) var(--vdw-ease);
}
</style>
