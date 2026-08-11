<script setup lang="ts">
/**
 * 全系统唯一的页面头部。视觉顺序固定，页面无法重排：
 *
 *   [返回] eyebrow（页面类型 / 对象 ID / 权限）
 *          h1（页面或对象名称）
 *          副信息（一句可读的状态摘要）
 *   末行：子页签（左） ──────────────── 页面操作（右）
 *
 * 重构前：数据集项目把页签放在 header 同行，大模型配置放在 header 下方，
 * 训练任务没有页签——三个页面三种结构。现在只有这一种。
 *
 * 三段都**定高且始终渲染**（eyebrow 22px、副信息 21px、末行 48px）。
 * 早期版本用 v-if 省掉空段，于是"有权限标签的项目页"比"没有的列表页"高
 * 几像素，标题和正文起点随页面漂移。定高换来的是跨页面完全一致的几何。
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
        <p class="page-header__eyebrow">
          <span class="page-header__tick" aria-hidden="true" />
          <span v-if="kind">{{ kind }}</span>
          <template v-if="code">
            <span class="page-header__slash" aria-hidden="true">/</span>
            <span>{{ code }}</span>
          </template>
          <slot name="eyebrow" />
        </p>
        <h1 data-test="page-title" :title="title">{{ title }}</h1>
        <p class="page-header__meta"><slot name="meta" /></p>
      </div>
    </div>
    <!-- 末行固定存在：左侧子页签、右侧页面操作。
         这样有页签和没页签的页面头部高度一致，正文起点不跳。 -->
    <div class="page-header__bar">
      <nav class="page-header__tabs" aria-label="页面子导航">
        <slot name="tabs" />
      </nav>
      <div class="page-header__actions"><slot name="actions" /></div>
    </div>
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

/* 定高 22px：权限标签等内容有自己的内距和边框，若让行高跟随内容，
   带标签的页面（数据集项目）会比不带的高几像素，标题和正文整体下移。
   这是"各页 header 位置略有不同"的直接原因。 */
.page-header__eyebrow {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 8px;
  height: 22px;
  margin: 0 0 3px;
  overflow: hidden;
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

/* 同样定高：有的页面没有副信息，若高度跟随内容，末行会整体上移 */
.page-header__meta {
  height: 21px;
  margin: 5px 0 0;
  overflow: hidden;
  color: var(--vdw-ink-2);
  font-size: 14px;
  white-space: nowrap;
  text-overflow: ellipsis;
}

/* 末行：左页签 + 右操作。行高由控件高度决定，两侧都空时仍占同一高度。 */
.page-header__bar {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  min-height: 48px;
  margin-top: 10px;
}

.page-header__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-left: auto;
  padding-bottom: 5px;
}

/* 页签永远在头部底边，与其它页面同位置同样式 */
.page-header__tabs {
  display: flex;
  flex: 1 1 auto;
  gap: 2px;
  min-width: 0;
  overflow-x: auto;
}

.page-header__tabs :deep(a),
.page-header__tabs :deep(button) {
  display: flex;
  align-items: center;
  gap: 7px;
  height: 43px;
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
