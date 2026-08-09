<script setup lang="ts">
/** 表格首列：ID 短标识 + 名称 + 一行副文本。全系统首列结构统一。 */
defineProps<{ name: string; sub?: string }>()
</script>

<template>
  <div class="vdw-cell-name">
    <div class="vdw-cell-name__line">
      <slot name="badge" />
      <b :title="name">{{ name }}</b>
      <slot name="after" />
    </div>
    <span v-if="sub || $slots.sub" :title="sub"><slot name="sub">{{ sub }}</slot></span>
  </div>
</template>

<style scoped>
.vdw-cell-name {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.vdw-cell-name__line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.vdw-cell-name b {
  overflow: hidden;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vdw-cell-name span {
  overflow: hidden;
  color: var(--vdw-ink-3);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
