<script setup lang="ts">
/**
 * 指标卡。取代 Overview 页四个只有数字和标签的 el-card。
 * 支持 to（可跳转，指标即导航入口）与 reticle（标记当前焦点对象）。
 */
import { RouterLink, type RouteLocationRaw } from 'vue-router'

withDefaults(defineProps<{
  label: string
  value: number | string
  unit?: string
  to?: RouteLocationRaw
  reticle?: boolean
}>(), { reticle: false })
</script>

<template>
  <component
    :is="to ? RouterLink : 'div'"
    :to="to"
    class="vdw-metric"
    :class="{ 'vdw-reticle': reticle, 'is-link': !!to }"
  >
    <div class="vdw-metric__label">{{ label }}</div>
    <div class="vdw-metric__value">
      {{ value }}<small v-if="unit">{{ unit }}</small>
    </div>
    <div v-if="$slots.default" class="vdw-metric__foot"><slot /></div>
  </component>
</template>

<style scoped>
.vdw-metric {
  display: block;
  min-width: 0;
  padding: 15px 16px;
  color: inherit;
  text-decoration: none;
  background: var(--vdw-surface);
  border: 1px solid var(--vdw-line);
  border-radius: var(--vdw-radius-card);
  transition: border-color var(--vdw-motion-fast) var(--vdw-ease),
    box-shadow var(--vdw-motion-fast) var(--vdw-ease);
}

.vdw-metric.is-link {
  cursor: pointer;
}

.vdw-metric.is-link:hover {
  border-color: var(--vdw-line-2);
  box-shadow: var(--vdw-shadow);
}

.vdw-metric__label {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--vdw-ink-3);
  font: 500 13px/1 var(--vdw-mono);
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.vdw-metric__value {
  margin-top: 11px;
  font: 500 30px/1 var(--vdw-mono);
  letter-spacing: -0.02em;
}

.vdw-metric__value small {
  margin-left: 4px;
  color: var(--vdw-ink-3);
  font-size: 15px;
  letter-spacing: 0;
}

.vdw-metric__foot {
  margin-top: 8px;
  color: var(--vdw-ink-2);
  font-size: 14px;
}
</style>
