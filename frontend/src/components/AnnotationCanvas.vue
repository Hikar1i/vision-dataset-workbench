<script setup lang="ts">
import Konva from 'konva'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { FrameAnnotation } from '../api/annotations'
import {
  clampBox,
  fitImage as calculateFit,
  stageToImage,
  zoomAtPoint,
  type BoxBounds,
  type Point,
} from '../views/annotationGeometry'

type CanvasLabel = { id: string; name: string; color: string }
type CanvasMode = 'select' | 'draw' | 'pan'
type NodeRef<T> = { getNode: () => T }

const props = defineProps<{
  imageUrl: string
  imageWidth: number
  imageHeight: number
  annotations: FrameAnnotation[]
  labels: CanvasLabel[]
  selectedId: string | null
  mode: CanvasMode
  readonly?: boolean
  crosshair?: boolean
  hiddenLabelIds?: string[]
}>()

const emit = defineEmits<{
  change: [items: FrameAnnotation[]]
  select: [id: string | null]
  'request-category': [bounds: BoxBounds, anchor: Point]
  'view-change': [viewport: BoxBounds]
}>()

const container = ref<HTMLElement | null>(null)
const stageRef = ref<NodeRef<Konva.Stage> | null>(null)
const transformerRef = ref<NodeRef<Konva.Transformer> | null>(null)
const stageSize = ref({ width: 1, height: 1 })
const image = ref<HTMLImageElement | null>(null)
const zoom = ref(1)
const pan = ref<Point>({ x: 0, y: 0 })
const pointer = ref<Point | null>(null)
const drawStart = ref<Point | null>(null)
const drawCurrent = ref<Point | null>(null)
const panStart = ref<{ pointer: Point; pan: Point } | null>(null)
let observer: ResizeObserver | null = null

const fit = computed(() =>
  calculateFit(
    stageSize.value.width,
    stageSize.value.height,
    props.imageWidth,
    props.imageHeight,
  ),
)
const groupConfig = computed(() => ({
  x: fit.value.x + pan.value.x,
  y: fit.value.y + pan.value.y,
  scaleX: fit.value.scale * zoom.value,
  scaleY: fit.value.scale * zoom.value,
}))
const labelMap = computed(() => new Map(props.labels.map((label) => [label.id, label])))
const visibleAnnotations = computed(() => {
  const hidden = new Set(props.hiddenLabelIds ?? [])
  return props.annotations.filter((item) => !hidden.has(item.label_id))
})
const preview = computed(() => {
  if (!drawStart.value || !drawCurrent.value) return null
  return {
    x: Math.min(drawStart.value.x, drawCurrent.value.x),
    y: Math.min(drawStart.value.y, drawCurrent.value.y),
    width: Math.abs(drawCurrent.value.x - drawStart.value.x),
    height: Math.abs(drawCurrent.value.y - drawStart.value.y),
  }
})
const cursor = computed(() => {
  if (props.mode === 'pan') return panStart.value ? 'grabbing' : 'grab'
  if (props.mode === 'draw') return 'crosshair'
  return 'default'
})
const zoomPercent = computed(() => Math.round(zoom.value * 100))

function loadImage() {
  const next = new Image()
  next.onload = () => { image.value = next }
  next.src = props.imageUrl
}

function updateStageSize() {
  if (!container.value) return
  const rect = container.value.getBoundingClientRect()
  stageSize.value = {
    width: Math.max(1, Math.round(rect.width)),
    height: Math.max(1, Math.round(rect.height)),
  }
}

function stagePoint(event: Konva.KonvaEventObject<Event>) {
  return event.target.getStage()?.getPointerPosition() ?? null
}

function imagePoint(event: Konva.KonvaEventObject<Event>) {
  const point = stagePoint(event)
  if (!point) return null
  return stageToImage(point, fit.value, zoom.value, pan.value)
}

function handlePointerDown(event: Konva.KonvaEventObject<MouseEvent>) {
  const point = stagePoint(event)
  if (!point) return
  if (props.mode === 'pan') {
    panStart.value = { pointer: point, pan: { ...pan.value } }
    return
  }
  if (props.mode === 'draw' && !props.readonly) {
    const start = imagePoint(event)
    if (start) drawStart.value = drawCurrent.value = start
    return
  }
  if (event.target === event.target.getStage()) emit('select', null)
}

function handlePointerMove(event: Konva.KonvaEventObject<MouseEvent>) {
  const point = stagePoint(event)
  pointer.value = point
  if (!point) return
  if (panStart.value) {
    pan.value = {
      x: panStart.value.pan.x + point.x - panStart.value.pointer.x,
      y: panStart.value.pan.y + point.y - panStart.value.pointer.y,
    }
  } else if (drawStart.value) {
    drawCurrent.value = imagePoint(event)
  }
}

function handlePointerUp() {
  panStart.value = null
  if (!drawStart.value || !drawCurrent.value) return
  const bounds = clampBox(
    {
      x_min: Math.min(drawStart.value.x, drawCurrent.value.x),
      y_min: Math.min(drawStart.value.y, drawCurrent.value.y),
      x_max: Math.max(drawStart.value.x, drawCurrent.value.x),
      y_max: Math.max(drawStart.value.y, drawCurrent.value.y),
    },
    props.imageWidth,
    props.imageHeight,
  )
  drawStart.value = drawCurrent.value = null
  if (bounds) emit('request-category', bounds, pointer.value ?? { x: 24, y: 24 })
}

function handleWheel(event: Konva.KonvaEventObject<WheelEvent>) {
  if (!event.evt.ctrlKey) return
  event.evt.preventDefault()
  const point = stagePoint(event)
  if (!point) return
  const factor = event.evt.deltaY > 0 ? 0.9 : 1.1
  const next = zoomAtPoint(point, fit.value, zoom.value, zoom.value * factor, pan.value)
  zoom.value = next.zoom
  pan.value = next.pan
}

function selectAnnotation(event: Konva.KonvaEventObject<MouseEvent>, id: string) {
  event.cancelBubble = true
  if (props.mode === 'select') emit('select', id)
}

function replaceBox(id: string, bounds: BoxBounds) {
  const next = clampBox(bounds, props.imageWidth, props.imageHeight)
  if (!next) return
  emit(
    'change',
    props.annotations.map((item) => (item.id === id ? { ...item, ...next } : { ...item })),
  )
}

function handleDragEnd(event: Konva.KonvaEventObject<DragEvent>, item: FrameAnnotation) {
  const node = event.target
  replaceBox(item.id, {
    x_min: node.x(),
    y_min: node.y(),
    x_max: node.x() + item.x_max - item.x_min,
    y_max: node.y() + item.y_max - item.y_min,
  })
}

function handleTransformEnd(event: Konva.KonvaEventObject<Event>, item: FrameAnnotation) {
  const node = event.target
  const width = Math.max(2, node.width() * node.scaleX())
  const height = Math.max(2, node.height() * node.scaleY())
  node.scaleX(1)
  node.scaleY(1)
  replaceBox(item.id, {
    x_min: node.x(),
    y_min: node.y(),
    x_max: node.x() + width,
    y_max: node.y() + height,
  })
}

function syncTransformer() {
  void nextTick(() => {
    const transformer = transformerRef.value?.getNode()
    const stage = stageRef.value?.getNode()
    const selected = props.selectedId
      ? stage?.findOne(`.annotation-${props.selectedId}`)
      : null
    transformer?.nodes(selected ? [selected] : [])
    transformer?.getLayer()?.batchDraw()
  })
}

function zoomBy(factor: number) {
  const point = { x: stageSize.value.width / 2, y: stageSize.value.height / 2 }
  const next = zoomAtPoint(point, fit.value, zoom.value, zoom.value * factor, pan.value)
  zoom.value = next.zoom
  pan.value = next.pan
}

function resetView() {
  zoom.value = 1
  pan.value = { x: 0, y: 0 }
}

function emitViewport() {
  const topLeft = stageToImage({ x: 0, y: 0 }, fit.value, zoom.value, pan.value)
  const bottomRight = stageToImage(
    { x: stageSize.value.width, y: stageSize.value.height },
    fit.value,
    zoom.value,
    pan.value,
  )
  emit('view-change', {
    x_min: Math.max(0, topLeft.x),
    y_min: Math.max(0, topLeft.y),
    x_max: Math.min(props.imageWidth, bottomRight.x),
    y_max: Math.min(props.imageHeight, bottomRight.y),
  })
}

watch(() => props.imageUrl, loadImage, { immediate: true })
watch(() => [props.selectedId, props.annotations, props.hiddenLabelIds], syncTransformer, {
  deep: true,
})
watch(() => [props.imageWidth, props.imageHeight], resetView)
watch([fit, zoom, pan, stageSize], emitViewport, { deep: true, immediate: true })

onMounted(() => {
  updateStageSize()
  observer = new ResizeObserver(updateStageSize)
  if (container.value) observer.observe(container.value)
})
onBeforeUnmount(() => observer?.disconnect())

defineExpose({ zoomBy, resetView, zoomPercent })
</script>

<template>
  <div
    ref="container"
    class="annotation-canvas"
    data-test="annotation-canvas"
    :style="{ cursor }"
  >
    <v-stage
      ref="stageRef"
      :config="stageSize"
      @mousedown="handlePointerDown"
      @mousemove="handlePointerMove"
      @mouseup="handlePointerUp"
      @mouseleave="handlePointerUp"
      @wheel="handleWheel"
    >
      <v-layer :config="{ listening: false }">
        <v-group :config="groupConfig">
          <v-image :config="{ image, width: imageWidth, height: imageHeight }" />
        </v-group>
      </v-layer>
      <v-layer>
        <v-group :config="groupConfig">
          <v-rect
            v-for="item in visibleAnnotations"
            :key="item.id"
            :config="{
              name: `annotation-${item.id}`,
              x: item.x_min,
              y: item.y_min,
              width: item.x_max - item.x_min,
              height: item.y_max - item.y_min,
              stroke: labelMap.get(item.label_id)?.color ?? '#ffca3a',
              strokeWidth: item.id === selectedId ? 3 : 2,
              strokeScaleEnabled: false,
              draggable: mode === 'select' && !readonly,
            }"
            @mousedown="selectAnnotation($event, item.id)"
            @dragend="handleDragEnd($event, item)"
            @transformend="handleTransformEnd($event, item)"
          />
          <v-rect
            v-if="preview"
            :config="{
              ...preview,
              stroke: '#78d2b8',
              strokeWidth: 2,
              dash: [8, 5],
              strokeScaleEnabled: false,
              listening: false,
            }"
          />
          <v-transformer
            ref="transformerRef"
            :config="{
              rotateEnabled: false,
              flipEnabled: false,
              enabledAnchors: ['top-left', 'top-right', 'bottom-left', 'bottom-right'],
              anchorSize: 8,
              borderStroke: '#78d2b8',
              anchorStroke: '#17212b',
              anchorFill: '#78d2b8',
              boundBoxFunc: (oldBox: unknown, newBox: { width: number; height: number }) =>
                Math.abs(newBox.width) < 2 || Math.abs(newBox.height) < 2 ? oldBox : newBox,
            }"
          />
        </v-group>
      </v-layer>
      <v-layer v-if="crosshair && pointer" :config="{ listening: false }">
        <v-line
          :config="{
            points: [0, pointer.y, stageSize.width, pointer.y],
            stroke: '#78d2b8',
            strokeWidth: 1,
            dash: [5, 5],
            opacity: 0.75,
          }"
        />
        <v-line
          :config="{
            points: [pointer.x, 0, pointer.x, stageSize.height],
            stroke: '#78d2b8',
            strokeWidth: 1,
            dash: [5, 5],
            opacity: 0.75,
          }"
        />
      </v-layer>
    </v-stage>
  </div>
</template>

<style scoped>
.annotation-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background:
    linear-gradient(45deg, #151d25 25%, transparent 25%) 0 0 / 18px 18px,
    linear-gradient(45deg, transparent 75%, #151d25 75%) 0 0 / 18px 18px,
    linear-gradient(45deg, transparent 75%, #151d25 75%) 9px -9px / 18px 18px,
    linear-gradient(45deg, #151d25 25%, #10171e 25%) 9px -9px / 18px 18px;
}
</style>
