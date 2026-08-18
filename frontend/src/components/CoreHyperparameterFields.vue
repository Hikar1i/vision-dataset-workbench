<script setup lang="ts">
import type { BatchMode } from '../api/hyperparameters'

defineProps<{
  epochs: number
  batchMode: BatchMode
  batchValue: number | null
  imageSize: number
  compact?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:epochs': [value: number]
  'update:batchMode': [value: BatchMode]
  'update:batchValue': [value: number | null]
  'update:imageSize': [value: number]
}>()

function changeBatchMode(value: BatchMode) {
  emit('update:batchMode', value)
  emit('update:batchValue', value === 'auto' ? null : value === 'fixed' ? 10 : 0.8)
}
</script>

<template>
  <div class="core-fields" :class="{ compact }">
    <el-form-item label="epochs">
      <el-input-number
        :model-value="epochs"
        :disabled="disabled"
        :min="1"
        :max="100000"
        :controls="false"
        @update:model-value="emit('update:epochs', Number($event))"
      />
    </el-form-item>
    <el-form-item :label="`image size · ${imageSize}`">
      <el-slider
        :model-value="imageSize"
        :disabled="disabled"
        :min="32"
        :max="1280"
        :step="32"
        show-stops
        @update:model-value="emit('update:imageSize', Number($event))"
      />
    </el-form-item>
    <el-form-item label="batch size" class="batch-field">
      <div class="batch-controls">
        <el-select
          :model-value="batchMode"
          :disabled="disabled"
          @update:model-value="changeBatchMode($event as BatchMode)"
        >
          <el-option label="自动" value="auto" />
          <el-option label="固定数量" value="fixed" />
          <el-option label="显存比例" value="fraction" />
        </el-select>
        <el-input-number
          :model-value="batchValue"
          :class="{ invisible: batchMode === 'auto' }"
          :disabled="disabled || batchMode === 'auto'"
          :min="batchMode === 'fixed' ? 1 : 0.01"
          :max="batchMode === 'fixed' ? 4096 : 1"
          :step="batchMode === 'fixed' ? 1 : 0.05"
          :precision="batchMode === 'fraction' ? 2 : 0"
          @update:model-value="emit('update:batchValue', $event == null ? null : Number($event))"
        />
      </div>
    </el-form-item>
  </div>
</template>

<style scoped>
.core-fields {
  display: grid;
  grid-template-columns: minmax(180px, 0.8fr) minmax(300px, 1.6fr);
  gap: 4px 22px;
}

.batch-field {
  grid-column: 1 / -1;
}

.batch-controls {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(180px, 1fr);
  gap: 14px;
}

.invisible {
  visibility: hidden;
  pointer-events: none;
}

.core-fields.compact {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.compact .batch-controls {
  grid-template-columns: 1fr;
}

@media (prefers-reduced-motion: reduce) {
  .core-fields * {
    transition: none !important;
  }
}
</style>
