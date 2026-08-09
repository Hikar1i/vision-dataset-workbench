<script setup lang="ts">
/** 统一卡片。取代各页面自写的 .create-panel / .resource-index / el-card。 */
withDefaults(defineProps<{
  title?: string
  /** 无内距，用于内部直接放 VTable */
  flush?: boolean
}>(), { flush: false })
</script>

<template>
  <section class="vdw-panel">
    <header v-if="title || $slots.head" class="vdw-panel__head">
      <h2 v-if="title">{{ title }}</h2>
      <slot name="head" />
      <div v-if="$slots.actions" class="vdw-panel__actions"><slot name="actions" /></div>
    </header>
    <div class="vdw-panel__body" :class="{ 'is-flush': flush }"><slot /></div>
    <footer v-if="$slots.footer" class="vdw-panel__footer"><slot name="footer" /></footer>
  </section>
</template>

<style scoped>
.vdw-panel {
  min-width: 0;
  background: var(--vdw-surface);
  border: 1px solid var(--vdw-line);
  border-radius: var(--vdw-radius-card);
}

.vdw-panel__head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 16px;
  border-bottom: 1px solid var(--vdw-line);
}

.vdw-panel__head h2 {
  font-size: 16px;
}

.vdw-panel__actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.vdw-panel__body {
  padding: 16px;
}

.vdw-panel__body.is-flush {
  padding: 0;
}

.vdw-panel__footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  background: var(--vdw-surface-2);
  border-top: 1px solid var(--vdw-line);
  border-radius: 0 0 var(--vdw-radius-card) var(--vdw-radius-card);
}
</style>
