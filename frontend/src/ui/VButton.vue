<script setup lang="ts">
/**
 * 全系统唯一的按钮。只有 4 种角色，页面无法表达"黄色按钮"或"绿色按钮"——
 * 这是风格不会再漂移的原因。取代 Element Plus 的
 * success / warning / info 实心按钮（重构前共 15 处）。
 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  /**
   * primary 实心近黑（每屏最多一个）· default 浅灰底中性次要动作 ·
   * quiet 无边框行内操作 · danger 危险操作
   *
   * 曾有一个 secondary 角色，语义是"指引下一步"。实测用户看不出这层含义，
   * 只觉得它和 primary 长得太像、分不出主次，已改名为 default 并压低视觉重量。
   */
  variant?: 'primary' | 'default' | 'quiet' | 'danger'
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
  variant: 'default',
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
  font-size: 14px;
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

/* default：中性次要动作（弹窗取消、工具栏并列动作）。
   刻意不用白底 + 深边框——那样和 primary 的近黑实心只差一层反相，
   用户分不出主次。改为浅灰底 + 淡边框，和 primary 拉开明度差。 */
.vdw-btn--default {
  color: var(--vdw-ink);
  background: var(--vdw-surface-2);
  border-color: var(--vdw-line);
}

.vdw-btn--default:not(:disabled):hover {
  color: var(--vdw-accent-ink);
  background: var(--vdw-accent-soft);
  border-color: var(--vdw-accent-line);
}

.vdw-btn--default:not(:disabled):active {
  background: #cfe6ec;
  border-color: var(--vdw-accent);
}

/* quiet：列表行内操作。无边框，靠图标 + 文字表达可点击；
   hover 时才画出底色与边框，让"这是按钮"在指针到达时确认。 */
.vdw-btn--quiet {
  padding: 0 9px;
  color: var(--vdw-ink-2);
}

.vdw-btn--quiet:not(:disabled):hover {
  color: var(--vdw-accent-ink);
  background: var(--vdw-accent-soft);
  border-color: var(--vdw-accent-line);
}

.vdw-btn--quiet:not(:disabled):active {
  background: #cfe6ec;
  border-color: var(--vdw-accent);
}

/* 行内图标：跟随文字色，尺寸固定，避免各页面自己调 */
.vdw-btn :deep(.el-icon) {
  flex: 0 0 auto;
  font-size: 15px;
}

.vdw-btn--sm :deep(.el-icon) {
  font-size: 14px;
}

/* danger：删除类。红字描边而非红底实心——列表里若每行都有红块，
   会盖过真正需要注意的状态色。确认弹窗才是拦住误删的那道关。 */
.vdw-btn--danger {
  color: var(--vdw-danger);
  background: var(--vdw-surface);
  border-color: var(--vdw-danger-line);
}

/* 行内 danger 不画边框，只用红字 + 图标，与同行 quiet 对齐；
   hover 时才显出红色轮廓。 */
.vdw-btn--danger.vdw-btn--sm {
  background: none;
  border-color: transparent;
}

.vdw-btn--danger.vdw-btn--sm:not(:disabled):hover {
  color: #fff;
  background: var(--vdw-danger);
  border-color: var(--vdw-danger);
}

.vdw-btn--danger:not(:disabled):hover {
  color: #fff;
  background: var(--vdw-danger);
  border-color: var(--vdw-danger);
}

.vdw-btn--danger:not(:disabled):active {
  background: var(--vdw-danger-hover);
}

/* 禁用态：靠**对比度**表达不可用，不靠删除线。
   删除线只是一条 1px 浅灰线，和可用按钮几乎分不出（实测用户反馈）；
   而文字 2.45:1 对 6.14:1 是 2.5 倍差距，扫一眼就能看出哪个点不了。
   同时降低图标透明度——图标比文字更吸引注意，必须一起压下去。
   两条都不是"只靠颜色"：还有 cursor: not-allowed 与 disabled 属性，
   读屏器与键盘用户从语义拿到同一信息。 */
.vdw-btn:disabled {
  color: var(--vdw-ink-disabled);
  background: var(--vdw-surface-2);
  border-color: var(--vdw-line);
  cursor: not-allowed;
  box-shadow: none;
}

.vdw-btn:disabled :deep(.el-icon) {
  opacity: 0.55;
}

/* 行内 quiet/danger 禁用后不画底色和边框：禁用项绝不能比可用项更显眼。
   重构前的实现正好相反（灰底描边方块比无底色的"详情"更抢眼）。 */
.vdw-btn--quiet:disabled,
.vdw-btn--danger.vdw-btn--sm:disabled {
  color: var(--vdw-ink-disabled);
  background: none;
  border-color: transparent;
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
