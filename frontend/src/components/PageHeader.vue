<script setup lang="ts">
/**
 * 全系统唯一的页面头部。视觉顺序固定，页面无法重排：
 *
 *   eyebrow（页面类型 / 对象 ID / 权限）
 *   h1（页面或对象名称）
 *   副信息（一句可读的状态摘要）
 *   操作区（右对齐，最多一个 primary）
 *   子页签（永远在头部底边）
 *
 * 重构前：数据集项目把页签放在 header 同行，大模型配置放在 header 下方，
 * 训练任务没有页签——三个页面三种结构。现在只有这一种。
 */
import { ArrowLeft } from '@element-plus/icons-vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

withDefaults(defineProps<{
  title: string
  /** 页面类型，显示在标题上方的等宽 eyebrow 里 */
  kind?: string
  /** 对象短 ID，跟在 kind 后面，例如 PROJECT / 128E0B */
  code?: string
  backTo?: RouteLocationRaw
  backLabel?: string
}>(), { backLabel: '返回上一页' })
</script>

<template>
  <header class="page-header">
    <div class="page-header__top">
      <RouterLink
        v-if="backTo"
        class="page-header__back"
        :to="backTo"
        :aria-label="backLabel"
        :title="backLabel"
      >
        <el-icon><ArrowLeft /></el-icon>
      </RouterLink>
      <div class="page-header__id">
        <p v-if="kind || code || $slots.eyebrow" class="page-header__eyebrow">
          <span class="page-header__tick" aria-hidden="true" />
          <span v-if="kind">{{ kind }}</span>
          <template v-if="code">
            <span class="page-header__slash" aria-hidden="true">/</span>
            <span>{{ code }}</span>
          </template>
          <slot name="eyebrow" />
        </p>
        <h1 data-test="page-title" :title="title">{{ title }}</h1>
        <p v-if="$slots.meta" class="page-header__meta"><slot name="meta" /></p>
      </div>
      <div v-if="$slots.actions" class="page-header__actions"><slot name="actions" /></div>
    </div>
    <nav v-if="$slots.tabs" class="page-header__tabs" aria-label="页面子导航">
      <slot name="tabs" />
    </nav>
  </header>
</template>

<style scoped>
.page-header {
  padding: 18px 24px 0;
  background: var(--vdw-surface);
  border-bottom: 1px solid var(--vdw-line);
}

.page-header__top {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  min-width: 0;
}

.page-header__back {
  display: grid;
  flex: 0 0 var(--vdw-control-height);
  place-items: center;
  width: var(--vdw-control-height);
  height: var(--vdw-control-height);
  margin-top: 2px;
  color: var(--vdw-ink);
  text-decoration: none;
  background: var(--vdw-surface);
  border: 1px solid var(--vdw-line-2);
  border-radius: var(--vdw-radius-control);
  transition: color var(--vdw-motion-fast) var(--vdw-ease),
    background-color var(--vdw-motion-fast) var(--vdw-ease),
    border-color var(--vdw-motion-fast) var(--vdw-ease);
}

.page-header__back:hover {
  color: var(--vdw-accent-ink);
  background: var(--vdw-accent-soft);
  border-color: var(--vdw-accent);
}

.page-header__id {
  min-width: 0;
}

.page-header__eyebrow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0 0 5px;
  color: var(--vdw-ink-3);
  font: 500 13px/1 var(--vdw-mono);
  letter-spacing: 0.11em;
  text-transform: uppercase;
}

.page-header__tick {
  width: 14px;
  height: 1px;
  background: var(--vdw-line-2);
}

.page-header__slash {
  color: var(--vdw-line-2);
}

.page-header h1 {
  min-width: 0;
  overflow: hidden;
  font-size: 24px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-header__meta {
  margin: 6px 0 0;
  color: var(--vdw-ink-2);
  font-size: 14px;
}

.page-header__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-left: auto;
  padding-top: 2px;
}

/* 页签永远在头部底边，与其它页面同位置同样式 */
.page-header__tabs {
  display: flex;
  gap: 2px;
  margin-top: 16px;
  overflow-x: auto;
}

.page-header__tabs :deep(a),
.page-header__tabs :deep(button) {
  display: flex;
  align-items: center;
  gap: 7px;
  height: 37px;
  padding: 0 15px;
  color: var(--vdw-ink-2);
  font: 500 14px/1 var(--vdw-sans);
  white-space: nowrap;
  text-decoration: none;
  background: none;
  border: 0;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color var(--vdw-motion-fast) var(--vdw-ease),
    background-color var(--vdw-motion-fast) var(--vdw-ease),
    border-color var(--vdw-motion-fast) var(--vdw-ease);
}

.page-header__tabs :deep(a:hover),
.page-header__tabs :deep(button:hover) {
  color: var(--vdw-ink);
  background: var(--vdw-surface-2);
}

.page-header__tabs :deep(.router-link-active),
.page-header__tabs :deep(.is-active),
.page-header__tabs :deep([aria-selected='true']) {
  color: var(--vdw-accent-ink);
  border-bottom-color: var(--vdw-accent);
}

/* 页签计数即导航信息，不是装饰 */
.page-header__tabs :deep(.tab-count) {
  color: var(--vdw-ink-3);
  font: 500 13px/1 var(--vdw-mono);
}

.page-header__tabs :deep(.router-link-active .tab-count),
.page-header__tabs :deep(.is-active .tab-count) {
  color: var(--vdw-accent);
}
</style>
