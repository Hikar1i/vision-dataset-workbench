<script setup lang="ts">
/** VTable 的行。列宽必须与父表 columns 一致。 */
defineProps<{ columns: string; recent?: boolean }>()
</script>

<template>
  <div
    class="vdw-table__row"
    :class="{ 'vdw-row--recent': recent }"
    role="row"
    :aria-current="recent ? 'true' : undefined"
    :style="{ gridTemplateColumns: columns }"
  >
    <slot />
  </div>
</template>

<style scoped>
.vdw-table__row {
  display: grid;
  gap: 16px;
  align-items: center;
  min-width: 0;
  min-height: var(--vdw-row-height);
  /* 行内上下内边距：信息密度高的台账需要呼吸空间，否则用户扫读时难以分辨行边界 */
  padding: 12px 16px;
  border-bottom: 1px solid var(--vdw-line);
}

/* 全列左对齐，间隔交给 16px 列间距。居中或右对齐会让每列视觉起点不同，
   扫读时眼睛要来回找；这条在原语里定死，页面不需要（也不应该）各自声明。 */
.vdw-table__row > :deep(*) {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  justify-self: stretch;
  text-align: left;
}
</style>
