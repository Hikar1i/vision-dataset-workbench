<script setup lang="ts">
/** VTable 的行。列宽必须与父表 columns 一致。 */
defineProps<{ columns: string }>()
</script>

<template>
  <div class="vdw-table__row" role="row" :style="{ gridTemplateColumns: columns }">
    <slot />
  </div>
</template>

<style scoped>
.vdw-table__row {
  display: grid;
  gap: 16px;
  align-items: center;
  min-height: var(--vdw-row-height);
  /* 行内上下内边距：信息密度高的台账需要呼吸空间，否则用户扫读时难以分辨行边界 */
  padding: 12px 16px;
  border-bottom: 1px solid var(--vdw-line);
}
</style>
