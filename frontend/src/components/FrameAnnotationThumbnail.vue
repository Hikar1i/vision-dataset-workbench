<script setup lang="ts">
import { formatFrameTimestamp } from './framePresentation'

type PreviewAnnotation = {
  id: string
  label_id: string
  x_min: number
  y_min: number
  x_max: number
  y_max: number
}

defineProps<{
  imageUrl: string
  imageWidth: number
  imageHeight: number
  annotations: PreviewAnnotation[]
  labelColors: Record<string, string>
  sequence: number
  timeOffset: number
  current?: boolean
  disabled?: boolean
}>()
</script>

<template>
  <div class="frame-thumbnail" :class="{ current, disabled }">
    <img loading="lazy" :src="imageUrl" alt="" />
    <svg
      v-if="annotations.length && imageWidth > 0 && imageHeight > 0"
      class="annotation-preview"
      :viewBox="`0 0 ${imageWidth} ${imageHeight}`"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      <rect
        v-for="item in annotations"
        :key="item.id"
        :x="item.x_min"
        :y="item.y_min"
        :width="Math.max(1, item.x_max - item.x_min)"
        :height="Math.max(1, item.y_max - item.y_min)"
        :stroke="labelColors[item.label_id] ?? 'var(--vdw-warn)'"
        vector-effect="non-scaling-stroke"
      />
    </svg>
    <span class="timestamp">{{ formatFrameTimestamp(timeOffset) }}</span>
    <span class="sequence">#{{ sequence }}</span>
    <span class="frame-status" :class="disabled ? 'is-disabled' : 'is-enabled'">{{ disabled ? '已停用' : '已启用' }}</span>
  </div>
</template>

<style scoped>
.frame-thumbnail {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: var(--vdw-focus-canvas);
}

.frame-thumbnail img,
.annotation-preview {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.frame-thumbnail img { object-fit: contain; }
.annotation-preview { pointer-events: none; }
.annotation-preview rect { fill: transparent; stroke-width: 1.25px; }

.frame-thumbnail.disabled::after {
  position: absolute;
  inset: 0;
  content: '';
  background: rgb(5 9 12 / 52%);
  pointer-events: none;
}

.timestamp,
.sequence,
.frame-status {
  position: absolute;
  z-index: 1;
  padding: 2px 5px;
  color: var(--vdw-surface-3);
  font: 13px var(--vdw-mono);
}

.timestamp { top: 4px; right: 4px; background: rgb(7 12 16 / 78%); }
.sequence { right: 4px; bottom: 4px; background: rgb(7 12 16 / 78%); }
.frame-status { bottom: 4px; left: 4px; }

/* 青色亮度高，承载不了白字（实测 2.06:1）。青底必须配深字：这里 8.1:1。
   停用的红底白字本身有 4.9:1，保持不变，两者形状一致、都达标。 */
.frame-status.is-enabled {
  color: var(--vdw-focus-canvas);
  background: var(--vdw-focus-accent);
}

.frame-status.is-disabled { background: var(--vdw-danger); }
</style>
