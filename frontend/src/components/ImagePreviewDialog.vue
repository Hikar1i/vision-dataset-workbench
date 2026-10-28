<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeftBold, ArrowRightBold, Close, Hide, Refresh, View, ZoomIn, ZoomOut } from '@element-plus/icons-vue'
import type { ImageAsset } from '../api/images'
import { imageFileUrl } from '../api/images'
import { fitImage, stageToImage, zoomAtPoint, type Point } from '../views/annotationGeometry'
import VButton from '../ui/VButton.vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  projectId: string
  image: ImageAsset | null
  directoryName: string
  labelColors: Record<string, string>
  labelNames?: Record<string, string>
  canEdit: boolean
  locked: boolean
  showAnnotationAction?: boolean
  previousDisabled?: boolean
  nextDisabled?: boolean
  navigating?: boolean
  positionLabel?: string
}>(), { showAnnotationAction: true, previousDisabled: true, nextDisabled: true, navigating: false, positionLabel: '', labelNames: () => ({}) })
const emit = defineEmits<{
  'update:modelValue': [boolean]
  annotate: [ImageAsset]
  enabled: [ImageAsset, boolean]
  navigate: [offset: number]
}>()

const showBoxes = ref(true)
const failed = ref(false)
const loading = ref(true)
const retry = ref(0)
const stage = ref<HTMLElement | null>(null)
const stageSize = ref({ width: 1, height: 1 })
const zoom = ref(1)
const pan = ref<Point>({ x: 0, y: 0 })
const drag = ref<{ pointer: Point; pan: Point; pointerId: number } | null>(null)
let observer: ResizeObserver | null = null
const width = computed(() => Math.max(1, props.image?.width ?? 1))
const height = computed(() => Math.max(1, props.image?.height ?? 1))
const dimensions = computed(() => `${width.value} × ${height.value}`)
const imageUrl = computed(() => props.image
  ? `${imageFileUrl(props.projectId, props.image.id)}${retry.value ? `?preview_retry=${retry.value}` : ''}`
  : '')
const fit = computed(() => fitImage(stageSize.value.width, stageSize.value.height, width.value, height.value, 24))
const transform = computed(() => ({
  width: `${width.value}px`, height: `${height.value}px`,
  transform: `translate(${fit.value.x + pan.value.x}px, ${fit.value.y + pan.value.y}px) scale(${fit.value.scale * zoom.value})`,
}))
const viewport = computed(() => {
  const topLeft = stageToImage({ x: 0, y: 0 }, fit.value, zoom.value, pan.value)
  const bottomRight = stageToImage({ x: stageSize.value.width, y: stageSize.value.height }, fit.value, zoom.value, pan.value)
  const x = Math.min(width.value, Math.max(0, topLeft.x))
  const y = Math.min(height.value, Math.max(0, topLeft.y))
  return { x, y, width: Math.max(0, Math.min(width.value, bottomRight.x) - x), height: Math.max(0, Math.min(height.value, bottomRight.y) - y) }
})
const writeDisabled = computed(() => !props.canEdit || props.locked || props.navigating || !props.image)
const writeTitle = computed(() => !props.canEdit ? '当前为只读权限' : props.locked ? '数据任务执行中，暂不可修改' : props.navigating ? '正在切换图片' : '')
const annotations = computed(() => {
  const fontSize = 13 / Math.max(0.001, fit.value.scale * zoom.value)
  return (props.image?.annotations ?? []).map((item, index) => {
    const name = props.labelNames[item.label_id]
    const title = name ? `${name} #${index + 1}` : `目标 ${index + 1}`
    const labelWidth = fontSize * (title.length + 1)
    const labelHeight = fontSize * 1.5
    return { ...item, title, fontSize, labelWidth, labelHeight,
      labelX: Math.max(0, Math.min(item.x_min, width.value - labelWidth)),
      labelY: Math.max(0, item.y_min - labelHeight),
      color: props.labelColors[item.label_id] ?? 'var(--vdw-warn)',
    }
  })
})

function stopDrag() {
  const pointerId = drag.value?.pointerId
  drag.value = null
  if (pointerId !== undefined && stage.value?.hasPointerCapture?.(pointerId)) stage.value.releasePointerCapture(pointerId)
}
function resetView() {
  stopDrag()
  zoom.value = 1
  pan.value = { x: 0, y: 0 }
}
function clampPan(value: Point): Point {
  const scale = fit.value.scale * zoom.value
  const clampAxis = (value: number, size: number, offset: number, rendered: number) => {
    const edge = Math.min(36, size / 2, rendered)
    return Math.min(size - edge - offset, Math.max(edge - offset - rendered, value))
  }
  return {
    x: clampAxis(value.x, stageSize.value.width, fit.value.x, width.value * scale),
    y: clampAxis(value.y, stageSize.value.height, fit.value.y, height.value * scale),
  }
}
function measureStage() {
  const rect = stage.value?.getBoundingClientRect()
  if (!rect || !props.modelValue) return
  stageSize.value = { width: Math.max(1, rect.width), height: Math.max(1, rect.height) }
  stopDrag()
  pan.value = zoom.value === 1 ? { x: 0, y: 0 } : clampPan(pan.value)
}
function observeStage() {
  observer?.disconnect()
  measureStage()
  if (stage.value && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(measureStage)
    observer.observe(stage.value)
  }
}
watch(stage, observeStage, { flush: 'post' })
watch([() => props.modelValue, () => props.projectId, () => props.image?.id], () => {
  resetView()
  failed.value = false
  loading.value = Boolean(props.modelValue && props.image)
  retry.value = 0
}, { immediate: true })
watch(() => props.modelValue, open => {
  if (open) showBoxes.value = true
  else observer?.disconnect()
})
function retryImage() {
  failed.value = false
  loading.value = true
  retry.value++
}
function imageLoaded(event: Event) {
  if ((event.currentTarget as Element).getAttribute('href') !== imageUrl.value) return
  loading.value = false
  failed.value = false
}
function imageFailed(event: Event) {
  if ((event.currentTarget as Element).getAttribute('href') !== imageUrl.value) return
  loading.value = false
  failed.value = true
}
function changeZoom(delta: number, point = { x: stageSize.value.width / 2, y: stageSize.value.height / 2 }) {
  const target = Math.min(5, Math.max(0.2, Number((zoom.value + delta).toFixed(2))))
  const next = zoomAtPoint(point, fit.value, zoom.value, target, pan.value)
  stopDrag()
  zoom.value = target
  pan.value = target === 1 ? { x: 0, y: 0 } : clampPan(next.pan)
}
function wheel(event: WheelEvent) {
  if (!event.ctrlKey) return
  event.preventDefault()
  const rect = stage.value?.getBoundingClientRect()
  if (rect) changeZoom(event.deltaY < 0 ? 0.1 : -0.1, { x: event.clientX - rect.left, y: event.clientY - rect.top })
}
function startDrag(event: PointerEvent) {
  if (zoom.value <= 1 || event.button !== 0 || failed.value || loading.value) return
  drag.value = { pointer: { x: event.clientX, y: event.clientY }, pan: { ...pan.value }, pointerId: event.pointerId }
  stage.value?.setPointerCapture?.(event.pointerId)
  event.preventDefault()
}
function moveDrag(event: PointerEvent) {
  if (!drag.value || drag.value.pointerId !== event.pointerId) return
  pan.value = clampPan({ x: drag.value.pan.x + event.clientX - drag.value.pointer.x, y: drag.value.pan.y + event.clientY - drag.value.pointer.y })
}
function endDrag(event: PointerEvent) {
  if (drag.value?.pointerId === event.pointerId) stopDrag()
}
function navigate(offset: number) {
  if (!props.modelValue || !props.image || props.navigating || (offset < 0 ? props.previousDisabled : props.nextDisabled)) return
  emit('navigate', offset)
}
function toggleEnabled() {
  if (!writeDisabled.value && props.image) emit('enabled', props.image, !props.image.enabled)
}
function annotate() {
  if (props.showAnnotationAction && !writeDisabled.value && props.image) emit('annotate', props.image)
}
function onKey(event: KeyboardEvent) {
  if (!props.modelValue || !props.image || event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return
  if (event.target instanceof Element && event.target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="combobox"]')) return
  switch (event.key.toLowerCase()) {
    case 'a': navigate(-1); break
    case 'd': navigate(1); break
    case 'r': resetView(); break
    case 'h': if (!event.repeat) showBoxes.value = !showBoxes.value; break
    case 's': if (!event.repeat) toggleEnabled(); break
    case 'w': if (!event.repeat) annotate(); break
    default: return
  }
  event.preventDefault()
  event.stopImmediatePropagation()
}
onMounted(() => {
  window.addEventListener('keydown', onKey, true)
  window.addEventListener('resize', measureStage)
})
onBeforeUnmount(() => {
  stopDrag()
  observer?.disconnect()
  window.removeEventListener('keydown', onKey, true)
  window.removeEventListener('resize', measureStage)
})
</script>

<template>
  <el-dialog append-to-body fullscreen :modal="false" class="image-preview-dialog vdw-dark" :model-value="modelValue" title="图片预览" :show-close="false" :close-on-click-modal="false" destroy-on-close @opened="observeStage" @update:model-value="emit('update:modelValue', $event)">
    <template #header="{ titleId }">
      <header class="preview-header vdw-dark">
        <div class="preview-info"><strong :id="titleId">图片预览</strong><span v-if="positionLabel">{{ positionLabel }}</span><span v-if="image" :class="image.enabled ? 'enabled-status' : 'disabled-status'">{{ image.enabled ? '已启用' : '已停用' }}</span><span v-if="navigating" role="status">正在切换图片…</span></div>
        <VButton variant="quiet" icon-only label="关闭图片预览" @click="emit('update:modelValue', false)"><template #icon><el-icon><Close /></el-icon></template></VButton>
      </header>
    </template>
    <section v-if="image" class="image-preview vdw-dark" data-test="image-preview">
      <div class="preview-workspace">
        <div ref="stage" class="preview-stage" data-test="preview-stage" :class="{ pannable: zoom > 1, dragging: drag }" @wheel="wheel" @pointerdown="startDrag" @pointermove="moveDrag" @pointerup="endDrag" @pointercancel="endDrag" @lostpointercapture="endDrag">
          <svg :key="`${projectId}/${image.id}/${retry}`" class="preview-image" data-test="preview-image" :class="{ 'boxes-hidden': !showBoxes }" :style="transform" :viewBox="`0 0 ${width} ${height}`" role="img" :aria-label="image.file_name">
            <image :href="imageUrl" :width="width" :height="height" @load="imageLoaded" @error="imageFailed"/>
            <g v-if="showBoxes && !failed" class="annotation-layer">
              <g v-for="item in annotations" :key="item.id">
                <title>{{ item.label_id }}</title>
                <rect class="preview-annotation-box" :x="item.x_min" :y="item.y_min" :width="item.x_max-item.x_min" :height="item.y_max-item.y_min" :stroke="item.color" :fill="item.color" fill-opacity="0.12" vector-effect="non-scaling-stroke"/>
                <g :transform="`translate(${item.labelX} ${item.labelY})`">
                  <rect :width="item.labelWidth" :height="item.labelHeight" fill="var(--vdw-focus-panel)" :stroke="item.color" vector-effect="non-scaling-stroke"/>
                  <text :x="item.fontSize * .35" :y="item.fontSize * 1.1" :font-size="item.fontSize" fill="var(--vdw-focus-ink)" font-weight="700">{{ item.title }}</text>
                </g>
              </g>
            </g>
          </svg>
          <div v-if="loading" class="preview-message" role="status">正在加载图片…</div>
          <div v-if="failed" class="preview-message preview-error" role="alert"><p>图片加载失败，请重试或切换到其他图片。</p><VButton @click="retryImage"><el-icon><Refresh/></el-icon>重新加载图片</VButton></div>
        </div>
        <aside class="preview-sidebar">
          <section class="preview-metadata"><h3>{{ image.file_name }}</h3><dl>
            <dt>目录</dt><dd>{{ directoryName }}</dd>
            <dt>来源路径</dt><dd>{{ image.source_relative_path }}</dd>
            <dt>尺寸</dt><dd>{{ dimensions }}</dd>
            <dt>大小</dt><dd>{{ image.file_size >= 1024*1024 ? `${(image.file_size/1024/1024).toFixed(1)} MB` : `${(image.file_size/1024).toFixed(1)} KB` }}</dd>
            <dt>标注</dt><dd>{{ image.annotations.length ? `${new Set(image.annotations.map(item=>item.label_id)).size} 类 · ${image.annotations.length} 目标` : '无目标框' }}</dd>
            <dt>导入方式</dt><dd>{{ image.materialization }}</dd>
          </dl></section>
          <section class="preview-minimap" data-test="preview-minimap">
            <header><strong>缩略图</strong><span>{{ Math.round(zoom*100) }}%</span></header>
            <svg :viewBox="`0 0 ${width} ${height}`" :style="{ aspectRatio: `${width}/${height}` }" aria-label="当前大图视口位置" role="img">
              <image :href="imageUrl" :width="width" :height="height"/>
              <rect class="preview-viewport-box" v-bind="viewport" vector-effect="non-scaling-stroke"/>
            </svg>
          </section>
        </aside>
      </div>
      <footer class="preview-footer">
        <VButton data-test="preview-toggle-enabled" :variant="image.enabled ? 'danger' : 'default'" :disabled="writeDisabled" :title="writeTitle" @click="toggleEnabled">{{ image.enabled ? '停用图片' : '启用图片' }} · S</VButton>
        <VButton data-test="preview-previous" :disabled="previousDisabled || navigating" @click="navigate(-1)"><el-icon><ArrowLeftBold/></el-icon>上一张 · A</VButton>
        <VButton data-test="preview-next" :disabled="nextDisabled || navigating" @click="navigate(1)">下一张 · D<el-icon><ArrowRightBold/></el-icon></VButton>
        <VButton icon-only label="缩小" :disabled="zoom<=.2" @click="changeZoom(-.1)"><template #icon><el-icon><ZoomOut/></el-icon></template></VButton>
        <span data-test="preview-zoom">{{ Math.round(zoom*100) }}%</span>
        <VButton icon-only label="放大" data-test="preview-zoom-in" :disabled="zoom>=5" @click="changeZoom(.1)"><template #icon><el-icon><ZoomIn/></el-icon></template></VButton>
        <VButton @click="resetView"><el-icon><Refresh/></el-icon>重置 · R</VButton>
        <VButton :aria-pressed="!showBoxes" @click="showBoxes=!showBoxes"><el-icon><Hide v-if="showBoxes"/><View v-else/></el-icon>{{ showBoxes ? '隐藏标注框' : '显示标注框' }} · H</VButton>
        <VButton v-if="showAnnotationAction" :disabled="writeDisabled" :title="writeTitle" aria-keyshortcuts="W" @click="annotate">打开标注工作台 · W</VButton>
      </footer>
    </section>
    <p v-else class="preview-empty vdw-dark" role="status">未选择图片，请关闭预览后选择图片。</p>
  </el-dialog>
</template>

<style scoped>
:global(.image-preview-dialog.el-dialog){padding:0;border:0;background:rgb(2 6 9 / 80%);overflow:hidden}
:global(.image-preview-dialog .el-dialog__header){padding:0;margin:0}
:global(.image-preview-dialog .el-dialog__body){padding:0;height:calc(100dvh - 54px)}
.preview-header{display:flex;align-items:center;justify-content:space-between;height:54px;padding:0 18px;color:var(--vdw-focus-ink);background:var(--vdw-focus-panel);border-bottom:1px solid var(--vdw-focus-line)}
.preview-info{display:flex;align-items:center;gap:14px;min-width:0}.preview-info strong{font:650 15px var(--vdw-sans)}.preview-info span{font:13px var(--vdw-mono)}.preview-info .enabled-status,.preview-info .disabled-status{padding:3px 7px;font-size:14px;border-radius:2px}.enabled-status{color:var(--vdw-focus-canvas);background:var(--vdw-focus-accent)}.disabled-status{color:white;background:var(--vdw-danger)}
.image-preview{display:grid;grid-template-rows:minmax(0,1fr) 62px;height:100%;min-height:0;color:var(--vdw-focus-ink);background:transparent;font:15px/1.5 var(--vdw-sans)}
.preview-workspace{display:grid;grid-template-columns:minmax(0,1fr) 300px;min-height:0;overflow:hidden}.preview-stage{position:relative;min-width:0;min-height:0;overflow:hidden;touch-action:none;cursor:default;background:rgb(2 6 9 / 22%)}.preview-stage.pannable{cursor:grab}.preview-stage.dragging{cursor:grabbing}
.preview-image{position:absolute;top:0;left:0;display:block;max-width:none;max-height:none;overflow:hidden;transform-origin:0 0;transition:transform 120ms ease;background:rgb(17 24 32 / 55%);box-shadow:0 12px 40px rgb(0 0 0 / 70%)}.preview-stage.dragging .preview-image{transition:none}.annotation-layer{pointer-events:none}.preview-annotation-box{stroke-width:3px}
.preview-message{position:absolute;z-index:4;top:50%;left:50%;max-width:90%;padding:12px;color:var(--vdw-focus-ink);background:var(--vdw-focus-panel);border:1px solid var(--vdw-focus-line);transform:translate(-50%,-50%)}.preview-error{text-align:center}.preview-message p{margin:0 0 12px}
.preview-sidebar{display:flex;flex-direction:column;min-height:0;overflow:hidden;border-left:1px solid var(--vdw-focus-line);background:var(--vdw-focus-panel)}.preview-metadata{flex:1;min-height:0;overflow:auto;padding:18px}.preview-metadata h3{margin:0 0 16px;overflow-wrap:anywhere;font-size:15px}.preview-metadata dl{margin:0;display:grid;grid-template-columns:70px minmax(0,1fr);gap:10px}.preview-metadata dt{color:var(--vdw-focus-ink-2)}.preview-metadata dd{margin:0;overflow-wrap:anywhere}
.preview-minimap{flex:none;min-height:0;padding:12px;border-top:1px solid var(--vdw-focus-line)}.preview-minimap header{display:flex;align-items:center;justify-content:space-between;height:24px}.preview-minimap strong{font-size:14px}.preview-minimap span{color:var(--vdw-focus-ink-2);font:13px var(--vdw-mono)}.preview-minimap svg{display:block;width:100%;max-height:240px;background:var(--vdw-focus-canvas)}.preview-viewport-box{fill:rgb(120 210 184 / 10%);stroke:var(--vdw-focus-accent);stroke-width:2px}
.preview-footer{display:flex;align-items:center;justify-content:center;gap:8px;min-width:0;overflow-x:auto;padding:0 14px;white-space:nowrap;background:var(--vdw-focus-panel);border-top:1px solid var(--vdw-focus-line)}.preview-footer>span{color:var(--vdw-focus-ink-2);font:13px var(--vdw-mono);min-width:5ch;text-align:center}.preview-footer>.vdw-btn{flex:none}.preview-empty{display:grid;place-content:center;height:100%;margin:0;color:var(--vdw-focus-ink)}
@media(prefers-reduced-motion:reduce){.preview-image{transition:none}}
</style>
