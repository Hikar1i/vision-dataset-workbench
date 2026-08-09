<script setup lang="ts">
/**
 * 状态标签。状态不只靠颜色区分——每个标签同时有色点、文字和边框，
 * 满足"颜色不得作为唯一状态提示"。
 */
import type { Tone } from './status'

withDefaults(defineProps<{
  tone?: Tone
  /** 进行中状态的色点呼吸；全系统唯一的循环动画 */
  pulse?: boolean
}>(), { tone: 'idle' })
</script>

<template>
  <span class="vdw-tag" :class="`vdw-tag--${tone}`">
    <i class="vdw-tag__dot" :class="{ 'is-pulse': pulse ?? tone === 'run' }" aria-hidden="true" />
    <slot />
  </span>
</template>

<style scoped>
.vdw-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  /* 作为表格 grid 的直接子元素时，默认会被拉伸到整列宽——短文本配长胶囊很难看。
     宽度收紧到内容宽度，并在列内左对齐。 */
  width: fit-content;
  justify-self: start;
  height: 23px;
  padding: 0 9px;
  font: 500 13px/1 var(--vdw-sans);
  white-space: nowrap;
  border: 1px solid transparent;
  border-radius: 999px;
}

.vdw-tag__dot {
  width: 6px;
  height: 6px;
  flex: 0 0 6px;
  background: currentcolor;
  border-radius: 50%;
}

.vdw-tag__dot.is-pulse {
  animation: vdw-pulse 1.6s var(--vdw-ease) infinite;
}

@keyframes vdw-pulse {
  50% { opacity: 0.3; }
}

.vdw-tag--ok {
  color: var(--vdw-ok);
  background: var(--vdw-ok-soft);
  border-color: var(--vdw-ok-line);
}

.vdw-tag--run {
  color: var(--vdw-accent);
  background: var(--vdw-accent-soft);
  border-color: var(--vdw-accent-line);
}

.vdw-tag--warn {
  color: var(--vdw-warn);
  background: var(--vdw-warn-soft);
  border-color: var(--vdw-warn-line);
}

.vdw-tag--danger {
  color: var(--vdw-danger);
  background: var(--vdw-danger-soft);
  border-color: var(--vdw-danger-line);
}

.vdw-tag--idle {
  color: var(--vdw-ink-2);
  background: var(--vdw-surface-3);
  border-color: var(--vdw-line);
}

@media (prefers-reduced-motion: reduce) {
  .vdw-tag__dot.is-pulse { animation: none; }
}
</style>
