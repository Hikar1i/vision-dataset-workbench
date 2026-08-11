<script setup lang="ts">
/**
 * 统一台账表格。
 *
 * 重构前共有两套实现：3 个页面用 el-table，14 个页面各写一套 CSS grid 行，
 * 列宽、行高、表头字号、hover 反馈全部不同。这是全系统视觉不一致的结构性根源。
 *
 * 列宽由调用方用 `columns` 给出 grid-template-columns，其余（行高、表头、
 * 分隔线、hover、空状态）由本组件固定。
 */
defineProps<{
  /** grid-template-columns 值，例如 'minmax(240px,1.3fr) 110px 130px' */
  columns: string
  /** 表头文案；数量需与列数一致 */
  headers?: string[]
  /** 行是否可点击（显示指针与 hover 背景） */
  interactive?: boolean
}>()
</script>

<template>
  <div class="vdw-table" role="table">
    <div
      v-if="headers?.length"
      class="vdw-table__row vdw-table__head"
      role="row"
      :style="{ gridTemplateColumns: columns }"
    >
      <span v-for="(head, index) in headers" :key="index" role="columnheader">{{ head }}</span>
    </div>
    <div class="vdw-table__body" :class="{ 'is-interactive': interactive }">
      <slot />
    </div>
    <slot name="empty" />
  </div>
</template>

<style scoped>
.vdw-table {
  min-width: 0;
}

.vdw-table__row {
  display: grid;
  gap: 16px;
  align-items: center;
  min-height: var(--vdw-row-height);
  /* 行内上下内边距：信息密度高的台账需要呼吸空间，否则用户扫读时难以分辨行边界 */
  padding: 12px 16px;
  border-bottom: 1px solid var(--vdw-line);
}

.vdw-table__head {
  min-height: 40px;
  padding-top: 0;
  padding-bottom: 0;
  color: var(--vdw-ink-3);
  font: 500 14px/1 var(--vdw-sans);
  background: var(--vdw-surface-2);
  border-radius: var(--vdw-radius-card) var(--vdw-radius-card) 0 0;
}

/* 表头一律不折行：折行的表头会把行高撑高一倍，并让相邻列的基线错开。
   列不够宽时应该改表头文案或加宽该列，而不是让它换行。 */
.vdw-table__head > span {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

/* 最后一行不画分隔线，避免和面板边框叠成双线 */
.vdw-table__body :deep(.vdw-table__row:last-child) {
  border-bottom: 0;
}

.vdw-table__body.is-interactive :deep(.vdw-table__row) {
  cursor: pointer;
  transition: background-color var(--vdw-motion-fast) var(--vdw-ease);
}

/* hover 用背景表达，不用位移 */
.vdw-table__body.is-interactive :deep(.vdw-table__row:hover) {
  background: var(--vdw-surface-2);
}
</style>
