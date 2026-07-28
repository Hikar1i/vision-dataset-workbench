<script setup lang="ts">
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
  current?: boolean
  disabled?: boolean
}>()
</script>

<template>
  <div class="frame-thumbnail" :class="{ current, disabled }">
    <img loading="lazy" :src="imageUrl" alt="" />
    <svg
      v-if="imageWidth > 0 && imageHeight > 0"
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
        :stroke="labelColors[item.label_id] ?? '#ffca3a'"
        vector-effect="non-scaling-stroke"
      />
    </svg>
    <span class="sequence">#{{ sequence }}</span>
    <span v-if="disabled" class="disabled-badge">已停用</span>
  </div>
</template>

<style scoped>
.frame-thumbnail {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: #111820;
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

.sequence,
.disabled-badge {
  position: absolute;
  z-index: 1;
  bottom: 4px;
  padding: 2px 5px;
  color: #f3f7f8;
  font: 10px var(--vdw-mono);
}

.sequence { right: 4px; background: rgb(7 12 16 / 78%); }
.disabled-badge { left: 4px; background: #c83f49; }
</style>
