<script setup lang="ts">
/** 空状态。空屏是行动邀请，所以默认带一个动作插槽。 */
defineProps<{ title: string; note?: string }>()
</script>

<template>
  <div class="vdw-empty">
    <p class="vdw-empty__title">{{ title }}</p>
    <p v-if="note" class="vdw-empty__note">{{ note }}</p>
    <div v-if="$slots.default" class="vdw-empty__action"><slot /></div>
  </div>
</template>

<style scoped>
.vdw-empty {
  display: grid;
  place-items: center;
  gap: 6px;
  padding: 56px 20px;
  text-align: center;
}

.vdw-empty__title {
  margin: 0;
  color: var(--vdw-ink);
  font-weight: 500;
  font-size: 15px;
}

.vdw-empty__note {
  max-width: 46ch;
  margin: 0;
  color: var(--vdw-ink-2);
  font-size: 14px;
}

.vdw-empty__action {
  margin-top: 8px;
}
</style>
