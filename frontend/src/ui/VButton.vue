<script setup lang="ts">
/**
 * 全系统唯一的按钮。只有 4 种角色，页面无法表达"黄色按钮"或"绿色按钮"——
 * 这是风格不会再漂移的原因。取代 Element Plus 的
 * success / warning / info 实心按钮（重构前共 15 处）。
 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  /** primary 实心近黑 · secondary 白底描边 · quiet 无底色 · danger 危险 */
  variant?: 'primary' | 'secondary' | 'quiet' | 'danger'
  size?: 'md' | 'sm'
  disabled?: boolean
  loading?: boolean
  /** 仅图标时必须提供 label 作为无障碍名称 */
  iconOnly?: boolean
  label?: string
  type?: 'button' | 'submit'
  /** 传 href 时渲染为链接（下载、外部跳转），保持同一视觉 */
  href?: string
}>(), {
  variant: 'secondary',
  size: 'md',
  type: 'button',
})

const classes = computed(() => [
  'vdw-btn',
  `vdw-btn--${props.variant}`,
  props.size === 'sm' && 'vdw-btn--sm',
  props.iconOnly && 'vdw-btn--icon',
  props.loading && 'is-loading',
])
</script>

<template>
  <component
    :is="href ? 'a' : 'button'"
    :class="classes"
    :href="href"
    :type="href ? undefined : type"
    :disabled="href ? undefined : disabled || loading"
    :aria-disabled="href && (disabled || loading) ? 'true' : undefined"
    :aria-label="iconOnly ? label : undefined"
    :aria-busy="loading || undefined"
  >
    <span v-if="loading" class="vdw-btn__spinner" aria-hidden="true" />
    <slot v-else name="icon" />
    <span v-if="!iconOnly" class="vdw-btn__text"><slot /></span>
  </component>
</template>

<style scoped>
.vdw-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  height: var(--vdw-control-height);
  padding: 0 14px;
  font: 500 14px/1 var(--vdw-sans);
  white-space: nowrap;
  background: none;
  border: 1px solid transparent;
  border-radius: var(--vdw-radius-control);
  cursor: pointer;
  /* hover 只改颜色/边框/阴影，绝不产生位移 */
  transition: color var(--vdw-motion-fast) var(--vdw-ease),
    background-color var(--vdw-motion-fast) var(--vdw-ease),
    border-color var(--vdw-motion-fast) var(--vdw-ease),
    box-shadow var(--vdw-motion-fast) var(--vdw-ease);
}

a.vdw-btn {
  text-decoration: none;
}

.vdw-btn[aria-disabled='true'] {
  color: var(--vdw-ink-3);
  background: var(--vdw-surface-2);
  border-color: var(--vdw-line);
  pointer-events: none;
}

.vdw-btn :deep(svg) {
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
}

.vdw-btn--sm {
  height: var(--vdw-control-height-sm);
  padding: 0 10px;
  font-size: 13px;
}

.vdw-btn--icon {
  width: var(--vdw-control-height);
  padding: 0;
}

.vdw-btn--icon.vdw-btn--sm {
  width: var(--vdw-control-height-sm);
}

.vdw-btn--primary {
  color: #fff;
  background: var(--vdw-solid);
  border-color: var(--vdw-solid);
}

.vdw-btn--primary:not(:disabled):hover {
  background: var(--vdw-solid-hover);
  border-color: var(--vdw-solid-hover);
}

.vdw-btn--primary:not(:disabled):active {
  background: var(--vdw-solid-active);
}

.vdw-btn--secondary {
  color: var(--vdw-ink);
  background: var(--vdw-surface);
  border-color: var(--vdw-line-2);
}

.vdw-btn--secondary:not(:disabled):hover {
  color: var(--vdw-accent-ink);
  background: var(--vdw-accent-soft);
  border-color: var(--vdw-accent);
}

.vdw-btn--secondary:not(:disabled):active {
  background: #cfe6ec;
}

.vdw-btn--quiet {
  padding: 0 9px;
  color: var(--vdw-ink-2);
}

.vdw-btn--quiet:not(:disabled):hover {
  color: var(--vdw-accent-ink);
  background: var(--vdw-surface-3);
}

.vdw-btn--quiet:not(:disabled):active {
  background: var(--vdw-line);
}

.vdw-btn--danger {
  color: var(--vdw-danger);
  background: var(--vdw-surface);
  border-color: var(--vdw-danger-line);
}

.vdw-btn--danger:not(:disabled):hover {
  color: #fff;
  background: var(--vdw-danger);
  border-color: var(--vdw-danger);
}

.vdw-btn--danger:not(:disabled):active {
  background: var(--vdw-danger-hover);
}

.vdw-btn:disabled {
  color: var(--vdw-ink-3);
  background: var(--vdw-surface-2);
  border-color: var(--vdw-line);
  cursor: not-allowed;
  box-shadow: none;
}

/* 禁用态绝不能比可用态更显眼：行内 quiet 按钮禁用后不画底色和边框，
   只降对比并加删除线。重构前的实现正好相反。 */
.vdw-btn--quiet:disabled {
  background: none;
  border-color: transparent;
  text-decoration: line-through;
  text-decoration-color: var(--vdw-line-2);
}

.vdw-btn__spinner {
  width: 13px;
  height: 13px;
  border: 2px solid currentcolor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: vdw-spin 620ms linear infinite;
}

@keyframes vdw-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .vdw-btn__spinner { animation-duration: 1.6s; }
}
</style>
