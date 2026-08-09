<script setup lang="ts">
import { ArrowLeft } from '@element-plus/icons-vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

withDefaults(defineProps<{
  title: string
  backTo?: RouteLocationRaw
  backLabel?: string
}>(), { backLabel: '返回上一页' })
</script>

<template>
  <header class="page-header">
    <div class="page-header__main">
      <RouterLink
        v-if="backTo"
        class="page-header__back"
        :to="backTo"
        :aria-label="backLabel"
        :title="backLabel"
      >
        <el-icon><ArrowLeft /></el-icon>
      </RouterLink>
      <div class="page-header__identity">
        <div class="page-header__title-line">
          <h1>{{ title }}</h1>
          <div v-if="$slots.meta" class="page-header__meta"><slot name="meta" /></div>
        </div>
      </div>
      <div v-if="$slots.actions" class="page-header__actions"><slot name="actions" /></div>
    </div>
    <div v-if="$slots.stats" class="page-header__stats"><slot name="stats" /></div>
    <nav v-if="$slots.tabs" class="page-header__tabs" aria-label="页面子导航"><slot name="tabs" /></nav>
  </header>
</template>

<style scoped>
.page-header {
  position: relative;
  display: grid;
  gap: 14px;
  min-height: var(--vdm-content-toolbar-height);
  padding: 20px 24px 0;
  background: var(--vdw-surface-raised);
  border-bottom: 1px solid var(--vdw-rule);
}

.page-header::before {
  position: absolute;
  top: 22px;
  bottom: 22px;
  left: 0;
  width: 3px;
  background: var(--vdw-teal);
  content: '';
}

.page-header__main,
.page-header__title-line,
.page-header__actions,
.page-header__stats,
.page-header__tabs {
  display: flex;
  align-items: center;
}

.page-header__main {
  gap: 14px;
  min-width: 0;
}

.page-header__back {
  display: grid;
  flex: 0 0 40px;
  place-items: center;
  width: 40px;
  height: 40px;
  color: var(--vdw-ink);
  text-decoration: none;
  background: var(--vdw-surface);
  border: 1px solid var(--vdw-rule);
  border-radius: var(--vdm-radius-control);
  transition: color var(--vdm-motion-fast) ease,
    background-color var(--vdm-motion-fast) ease,
    border-color var(--vdm-motion-fast) ease,
    box-shadow var(--vdm-motion-fast) ease;
}

.page-header__back:hover {
  color: var(--vdw-teal-hover);
  background: #f0f7f5;
  border-color: #9fc9bf;
  box-shadow: 0 3px 10px rgb(24 43 55 / 10%);
}

.page-header__identity {
  min-width: 0;
}

.page-header__title-line {
  flex-wrap: wrap;
  gap: 8px 12px;
}

.page-header h1 {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  font: 700 26px/1.15 var(--vdw-title);
  letter-spacing: -0.025em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-header__meta,
.page-header__stats {
  color: var(--vdw-muted);
  font-size: 14px;
}

.page-header__actions {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  margin-left: auto;
}

.page-header__stats {
  gap: 16px;
}

.page-header__tabs {
  align-self: end;
  width: fit-content;
  max-width: 100%;
  gap: 4px;
  padding: 4px;
  overflow-x: auto;
  background: #edf3f6;
  border: 1px solid #d8e3e8;
  border-radius: var(--vdm-radius-card) var(--vdm-radius-card) 0 0;
}

.page-header__tabs :deep(a),
.page-header__tabs :deep(button) {
  display: grid;
  place-items: center;
  min-height: 36px;
  padding: 0 14px;
  color: var(--vdw-muted);
  font: 600 14px/1 var(--vdw-body);
  text-decoration: none;
  white-space: nowrap;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--vdm-radius-control);
  cursor: pointer;
  transition: color var(--vdm-motion-fast) ease,
    background-color var(--vdm-motion-fast) ease,
    border-color var(--vdm-motion-fast) ease,
    box-shadow var(--vdm-motion-fast) ease;
}

.page-header__tabs :deep(a:hover),
.page-header__tabs :deep(button:hover) {
  color: var(--vdw-ink);
  background: rgb(255 255 255 / 60%);
}

.page-header__tabs :deep(.active),
.page-header__tabs :deep(.router-link-active),
.page-header__tabs :deep([aria-selected='true']) {
  color: var(--vdw-teal-hover);
  background: var(--vdw-surface-raised);
  border-color: #c8d8df;
  box-shadow: 0 2px 7px rgb(24 43 55 / 10%);
}
</style>
