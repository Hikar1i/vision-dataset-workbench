<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeftBold,
  ArrowRightBold,
  Close,
  Hide,
  Refresh,
  View,
  ZoomIn,
  ZoomOut,
} from '@element-plus/icons-vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { getFrameAnnotations, type FrameAnnotation } from '../api/annotations'
import { listLabels, type ProjectLabel } from '../api/labels'
import {
  frameImageUrl,
  getFrameAnnotationSummary,
  listFrames,
  setFramesEnabled,
  type Frame,
  type SamplingSummary,
} from '../api/media'
import FrameAnnotationThumbnail from './FrameAnnotationThumbnail.vue'
import {
  applyEnabledPattern,
  diffEnabledStates,
  selectFrameRange,
  type EnabledState,
} from './frameFilter'
import { formatFrameTimestamp } from './framePresentation'
import {
  fitImage,
  stageToImage,
  zoomAtPoint,
  type BoxBounds,
  type Point,
} from '../views/annotationGeometry'

type PageSize = 50 | 100 | 200 | 'all'

const props = defineProps<{
  modelValue: boolean
  projectId: string
  videoId: string
  title: string
  canEdit: boolean
  imageWidth: number
  imageHeight: number
}>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; updated: [] }>()

const frames = ref<Frame[]>([])
const sampling = ref<SamplingSummary | null>(null)
const labels = ref<ProjectLabel[]>([])
const annotatedIds = ref(new Set<string>())
const baseline = ref<EnabledState>({})
const draft = ref<EnabledState>({})
const page = ref(1)
const pageSize = ref<PageSize>(100)
const selected = ref(new Set<string>())
const selectionAnchor = ref<string | null>(null)
const rangeMode = ref(false)
const loading = ref(false)
const saving = ref(false)
const analyzing = ref(false)
const error = ref('')

const patternOpen = ref(false)
const patternLength = ref(2)
const pattern = ref<boolean[]>([true, true])

const previewIndex = ref<number | null>(null)
const previewLoading = ref(false)
const previewZoom = ref(1)
const previewPan = ref<Point>({ x: 0, y: 0 })
const previewStage = ref<HTMLElement | null>(null)
const previewStageSize = ref({ width: 1, height: 1 })
const previewDrag = ref<{ pointer: Point; pan: Point; pointerId: number } | null>(null)
const boxesVisible = ref(true)
const showThumbnailAnnotations = ref(true)
const annotationCache = ref<Record<string, FrameAnnotation[]>>({})
let previewObserver: ResizeObserver | null = null

const orderedIds = computed(() => frames.value.map((frame) => frame.id))
const changes = computed(() => diffEnabledStates(orderedIds.value, baseline.value, draft.value))
const enabledCount = computed(() => frames.value.filter((frame) => draft.value[frame.id]).length)
const disabledCount = computed(() => frames.value.length - enabledCount.value)
const annotatedEnabledCount = computed(() => frames.value.filter(
  (frame) => annotatedIds.value.has(frame.id) && draft.value[frame.id],
).length)
const annotatedDisabledCount = computed(() => annotatedIds.value.size - annotatedEnabledCount.value)
const totalPages = computed(() => pageSize.value === 'all'
  ? 1
  : Math.max(1, Math.ceil(frames.value.length / pageSize.value)))
const visibleFrames = computed(() => {
  if (pageSize.value === 'all') return frames.value
  const start = (page.value - 1) * pageSize.value
  return frames.value.slice(start, start + pageSize.value)
})
const previewFrame = computed(() => previewIndex.value === null ? null : frames.value[previewIndex.value])
const previewAnnotations = computed(() => previewFrame.value
  ? (annotationCache.value[previewFrame.value.id] ?? [])
  : [])
const labelColors = computed(() => Object.fromEntries(labels.value.map((label) => [label.id, label.color])))
const labelMap = computed(() => new Map(labels.value.map((label) => [label.id, label])))
const previewFileName = computed(() => previewFrame.value ? frameFileName(previewFrame.value) : '')
const previewFit = computed(() => fitImage(
  previewStageSize.value.width,
  previewStageSize.value.height,
  props.imageWidth,
  props.imageHeight,
  24,
))
const previewTransform = computed(() => ({
  width: `${Math.max(1, props.imageWidth)}px`,
  height: `${Math.max(1, props.imageHeight)}px`,
  transform: `translate(${previewFit.value.x + previewPan.value.x}px, ${previewFit.value.y + previewPan.value.y}px) scale(${previewFit.value.scale * previewZoom.value})`,
}))
const previewViewport = computed<BoxBounds>(() => {
  const topLeft = stageToImage(
    { x: 0, y: 0 },
    previewFit.value,
    previewZoom.value,
    previewPan.value,
  )
  const bottomRight = stageToImage(
    { x: previewStageSize.value.width, y: previewStageSize.value.height },
    previewFit.value,
    previewZoom.value,
    previewPan.value,
  )
  const xMin = Math.min(props.imageWidth, Math.max(0, topLeft.x))
  const yMin = Math.min(props.imageHeight, Math.max(0, topLeft.y))
  const xMax = Math.min(props.imageWidth, Math.max(0, bottomRight.x))
  const yMax = Math.min(props.imageHeight, Math.max(0, bottomRight.y))
  return {
    x_min: Math.min(xMin, xMax),
    y_min: Math.min(yMin, yMax),
    x_max: Math.max(xMin, xMax),
    y_max: Math.max(yMin, yMax),
  }
})

watch(patternLength, (length) => {
  const next = pattern.value.slice(0, length)
  while (next.length < length) next.push(true)
  pattern.value = next
})
watch(pageSize, () => { page.value = 1 })
watch(() => props.modelValue, (open) => {
  if (open) void load()
  else resetTransientState()
}, { immediate: true })

async function load() {
  if (!props.videoId) return
  loading.value = true
  error.value = ''
  try {
    const [first, summary, projectLabels] = await Promise.all([
      listFrames(props.projectId, props.videoId, 1, 200, undefined, true),
      getFrameAnnotationSummary(props.projectId, props.videoId),
      listLabels(props.projectId),
    ])
    const pageCount = Math.ceil(first.total / first.page_size)
    const rest = pageCount > 1
      ? await Promise.all(Array.from({ length: pageCount - 1 }, (_, index) =>
          listFrames(props.projectId, props.videoId, index + 2, first.page_size, undefined, true)))
      : []
    frames.value = [first, ...rest].flatMap((item) => item.items)
    sampling.value = first.sampling
    labels.value = projectLabels
    annotatedIds.value = new Set(summary.annotated_frame_ids)
    baseline.value = Object.fromEntries(frames.value.map((frame) => [frame.id, frame.enabled]))
    draft.value = { ...baseline.value }
    page.value = 1
    selected.value = new Set()
    selectionAnchor.value = null
    rangeMode.value = false
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '采样帧加载失败'
  } finally {
    loading.value = false
  }
}

function resetTransientState() {
  previewIndex.value = null
  resetPreviewView()
  boxesVisible.value = true
  patternOpen.value = false
  rangeMode.value = false
  selected.value = new Set()
  selectionAnchor.value = null
  annotationCache.value = {}
}

function frameFileName(frame: Frame) {
  return `frame_${String(frame.sequence).padStart(6, '0')}.${sampling.value?.output_format ?? 'jpg'}`
}

function formatFileSize(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${(bytes / 1024).toFixed(1)} KB`
}

function annotationLabel(item: FrameAnnotation) {
  return labelMap.value.get(item.label_id)?.name ?? 'unknown'
}

function colorWithAlpha(color: string, alpha: number) {
  const value = color.match(/^#([0-9a-f]{6})$/i)?.[1]
  if (!value) return `rgb(255 202 58 / ${alpha})`
  const channels = [0, 2, 4].map((offset) => Number.parseInt(value.slice(offset, offset + 2), 16))
  return `rgb(${channels.join(' ')} / ${alpha})`
}

function contrastText(color: string) {
  const value = color.match(/^#([0-9a-f]{6})$/i)?.[1]
  if (!value) return '#111820'
  const [red, green, blue] = [0, 2, 4]
    .map((offset) => Number.parseInt(value.slice(offset, offset + 2), 16))
  return red * 0.299 + green * 0.587 + blue * 0.114 > 150 ? '#111820' : '#ffffff'
}

function annotationTitle(item: FrameAnnotation, index: number) {
  const base = `${annotationLabel(item)} #${index + 1}`
  return item.source === 'model' && item.confidence !== null
    ? `${base} · ${item.confidence.toFixed(2)}`
    : base
}

function annotationLabelSize(item: FrameAnnotation, index: number) {
  const fontSize = Math.max(24, props.imageWidth / 68)
  return {
    fontSize,
    height: fontSize * 1.45,
    width: Math.max(fontSize * 3.2, (annotationTitle(item, index).length + 1) * fontSize * 0.62),
  }
}

function toggleDraft(frameId: string) {
  if (!props.canEdit) return
  draft.value = { ...draft.value, [frameId]: !draft.value[frameId] }
}

function enterRangeMode() {
  rangeMode.value = true
  selected.value = new Set()
  selectionAnchor.value = null
}

function exitRangeMode() {
  rangeMode.value = false
  selected.value = new Set()
  selectionAnchor.value = null
}

function clearSelection() {
  selected.value = new Set()
  selectionAnchor.value = null
}

function selectFrame(frameId: string, event: MouseEvent) {
  if (event.shiftKey && selectionAnchor.value) {
    selected.value = selectFrameRange(
      orderedIds.value,
      selected.value,
      selectionAnchor.value,
      frameId,
    )
    return
  }
  const next = new Set(selected.value)
  next.has(frameId) ? next.delete(frameId) : next.add(frameId)
  selected.value = next
  selectionAnchor.value = frameId
}

function handleThumbnail(frame: Frame, event: MouseEvent) {
  if (rangeMode.value) selectFrame(frame.id, event)
  else void openPreview(frames.value.findIndex((item) => item.id === frame.id))
}

function setSelectedEnabled(enabled: boolean) {
  if (!selected.value.size) return
  draft.value = Object.fromEntries(frames.value.map((frame) => [
    frame.id,
    selected.value.has(frame.id) ? enabled : draft.value[frame.id],
  ]))
}

function togglePattern(index: number) {
  pattern.value = pattern.value.map((enabled, itemIndex) => itemIndex === index ? !enabled : enabled)
}

function applyPattern() {
  if (rangeMode.value && !selected.value.size) {
    ElMessage.warning('请先选择采样帧。')
    return
  }
  draft.value = applyEnabledPattern(
    orderedIds.value,
    draft.value,
    pattern.value,
    rangeMode.value ? selected.value : undefined,
  )
  patternOpen.value = false
  ElMessage.success('启停模板已应用到前端草稿。')
}

async function enableByAnnotation() {
  analyzing.value = true
  error.value = ''
  try {
    const summary = await getFrameAnnotationSummary(props.projectId, props.videoId)
    await ElMessageBox.confirm(
      '包含至少一个标注框的采样帧将启用，无标注框的采样帧将停用。该操作会覆盖当前前端草稿，是否继续？',
      '按标注启停',
      { type: 'warning', confirmButtonText: '确认覆盖', cancelButtonText: '取消', customClass: 'frame-filter-confirm' },
    )
    annotatedIds.value = new Set(summary.annotated_frame_ids)
    draft.value = Object.fromEntries(frames.value.map((frame) => [
      frame.id,
      annotatedIds.value.has(frame.id),
    ]))
  } catch (reason) {
    if (reason !== 'cancel' && reason !== 'close') {
      error.value = reason instanceof Error ? reason.message : '按标注启停失败'
    }
  } finally {
    analyzing.value = false
  }
}

async function saveChanges() {
  if (!sampling.value || !changes.value.length) return
  saving.value = true
  error.value = ''
  try {
    sampling.value = await setFramesEnabled(
      props.projectId,
      props.videoId,
      changes.value,
      sampling.value.frame_revision,
    )
    baseline.value = { ...draft.value }
    frames.value = frames.value.map((frame) => ({ ...frame, enabled: draft.value[frame.id] }))
    emit('updated')
    ElMessage.success('采样帧启停状态已保存。')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '采样帧启停状态保存失败'
  } finally {
    saving.value = false
  }
}

async function requestClose() {
  if (props.canEdit && changes.value.length) {
    try {
      await ElMessageBox.confirm(
        `还有 ${changes.value.length} 个采样帧的启停状态未保存，确定放弃这些修改吗？`,
        '放弃未保存修改',
        { type: 'warning', confirmButtonText: '放弃修改', cancelButtonText: '继续筛帧' },
      )
    } catch {
      return
    }
  }
  emit('update:modelValue', false)
}

async function loadPreviewAnnotations(frame: Frame) {
  if (annotationCache.value[frame.id]) return
  previewLoading.value = true
  try {
    const result = await getFrameAnnotations(props.projectId, props.videoId, frame.id)
    annotationCache.value = { ...annotationCache.value, [frame.id]: result.items }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '标注信息加载失败'
  } finally {
    previewLoading.value = false
  }
}

async function openPreview(index: number) {
  if (index < 0 || index >= frames.value.length) return
  previewIndex.value = index
  resetPreviewView()
  boxesVisible.value = true
  await nextTick()
  updatePreviewStageSize()
  observePreviewStage()
  await loadPreviewAnnotations(frames.value[index])
}

async function movePreview(offset: number) {
  if (previewIndex.value === null) return
  const next = previewIndex.value + offset
  if (next < 0 || next >= frames.value.length) return
  await openPreview(next)
}

function closePreview() {
  previewIndex.value = null
  resetPreviewView()
  previewObserver?.disconnect()
}

function zoomPreview(delta: number) {
  const point = {
    x: previewStageSize.value.width / 2,
    y: previewStageSize.value.height / 2,
  }
  const targetZoom = Math.min(5, Math.max(0.2, Number((previewZoom.value + delta).toFixed(2))))
  const next = zoomAtPoint(
    point,
    previewFit.value,
    previewZoom.value,
    targetZoom,
    previewPan.value,
  )
  previewZoom.value = targetZoom
  previewPan.value = targetZoom === 1 ? { x: 0, y: 0 } : clampPreviewPan(next.pan)
}

function handlePreviewWheel(event: WheelEvent) {
  if (!event.ctrlKey || previewIndex.value === null) return
  event.preventDefault()
  const rect = previewStage.value?.getBoundingClientRect()
  if (!rect) return
  const targetZoom = Math.min(5, Math.max(
    0.2,
    Number((previewZoom.value + (event.deltaY < 0 ? 0.1 : -0.1)).toFixed(2)),
  ))
  const next = zoomAtPoint(
    { x: event.clientX - rect.left, y: event.clientY - rect.top },
    previewFit.value,
    previewZoom.value,
    targetZoom,
    previewPan.value,
  )
  previewZoom.value = targetZoom
  previewPan.value = targetZoom === 1 ? { x: 0, y: 0 } : clampPreviewPan(next.pan)
}

function resetPreviewView() {
  previewZoom.value = 1
  previewPan.value = { x: 0, y: 0 }
  previewDrag.value = null
}

function updatePreviewStageSize() {
  const rect = previewStage.value?.getBoundingClientRect()
  if (!rect) return
  previewStageSize.value = {
    width: Math.max(1, Math.round(rect.width)),
    height: Math.max(1, Math.round(rect.height)),
  }
}

function observePreviewStage() {
  previewObserver?.disconnect()
  if (!previewStage.value || typeof ResizeObserver === 'undefined') return
  previewObserver = new ResizeObserver(updatePreviewStageSize)
  previewObserver.observe(previewStage.value)
}

function clampPreviewPan(pan: Point) {
  const scale = previewFit.value.scale * previewZoom.value
  const renderedWidth = props.imageWidth * scale
  const renderedHeight = props.imageHeight * scale
  const clampAxis = (value: number, stageSize: number, fitOffset: number, renderedSize: number) => {
    const visibleEdge = Math.min(36, stageSize / 2, renderedSize)
    const minimum = visibleEdge - fitOffset - renderedSize
    const maximum = stageSize - visibleEdge - fitOffset
    return Math.min(maximum, Math.max(minimum, value))
  }
  return {
    x: clampAxis(pan.x, previewStageSize.value.width, previewFit.value.x, renderedWidth),
    y: clampAxis(pan.y, previewStageSize.value.height, previewFit.value.y, renderedHeight),
  }
}

function startPreviewDrag(event: PointerEvent) {
  if (previewZoom.value <= 1 || (event.target as Element).closest('.preview-minimap')) return
  previewDrag.value = {
    pointer: { x: event.clientX, y: event.clientY },
    pan: { ...previewPan.value },
    pointerId: event.pointerId,
  }
  ;(event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId)
}

function movePreviewDrag(event: PointerEvent) {
  if (!previewDrag.value || previewDrag.value.pointerId !== event.pointerId) return
  previewPan.value = clampPreviewPan({
    x: previewDrag.value.pan.x + event.clientX - previewDrag.value.pointer.x,
    y: previewDrag.value.pan.y + event.clientY - previewDrag.value.pointer.y,
  })
}

function stopPreviewDrag(event?: PointerEvent) {
  if (event && previewDrag.value?.pointerId !== event.pointerId) return
  previewDrag.value = null
}

function isEditableTarget(target: EventTarget | null) {
  const element = target instanceof HTMLElement ? target : null
  return Boolean(element?.closest('input, textarea, select, [contenteditable="true"], .el-input'))
}

function handleKeydown(event: KeyboardEvent) {
  if (!props.modelValue || previewIndex.value === null || isEditableTarget(event.target)) return
  const key = event.key.toLowerCase()
  if (key === 'escape') closePreview()
  else if (key === 'a') void movePreview(-1)
  else if (key === 'd') void movePreview(1)
  else if (key === 'r') resetPreviewView()
  else if (key === 'h') boxesVisible.value = !boxesVisible.value
  else if (key === 's' && props.canEdit && previewFrame.value) toggleDraft(previewFrame.value.id)
  else return
  event.preventDefault()
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!changes.value.length) return
  event.preventDefault()
  event.returnValue = ''
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('beforeunload', handleBeforeUnload)
  window.addEventListener('resize', updatePreviewStageSize)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('beforeunload', handleBeforeUnload)
  window.removeEventListener('resize', updatePreviewStageSize)
  previewObserver?.disconnect()
})
</script>

<template>
  <el-dialog
    append-to-body
    class="frames-workbench-dialog"
    fullscreen
    :model-value="modelValue"
    :show-close="false"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
  >
    <template #header>
      <header class="focus-header">
        <div class="focus-title">
          <span data-test="frames-brand">VDM / FRAMES</span>
          <strong :title="title">{{ title }}</strong>
          <code>{{ frames.length ? `FRAME 1–${frames.length}` : 'FRAME —' }}</code>
        </div>
        <button type="button" title="关闭筛帧工作台" aria-label="关闭筛帧工作台" @click="requestClose">
          <el-icon><Close /></el-icon>
        </button>
      </header>
    </template>

    <main class="frames-workbench" :class="{ 'range-mode': rangeMode }">
      <section class="frames-toolbar">
        <div class="toolbar-left">
          <label>每页
            <el-select v-model="pageSize" class="page-size-select">
              <el-option label="50" :value="50" />
              <el-option label="100" :value="100" />
              <el-option label="200" :value="200" />
              <el-option label="全部" value="all" />
            </el-select>
          </label>
          <label>缩略图标注
            <el-switch v-model="showThumbnailAnnotations" data-test="thumbnail-annotations-switch" />
          </label>
          <template v-if="canEdit">
            <el-button v-if="!rangeMode" data-test="enter-range" @click="enterRangeMode">范围多选</el-button>
            <template v-else>
              <el-button @click="exitRangeMode">退出多选</el-button>
              <el-button :disabled="!selected.size" @click="clearSelection">取消选中</el-button>
              <el-button type="success" plain :disabled="!selected.size" @click="setSelectedEnabled(true)">批量启用</el-button>
              <el-button type="danger" plain :disabled="!selected.size" @click="setSelectedEnabled(false)">批量停用</el-button>
            </template>
            <el-button @click="patternOpen = true">启停模板</el-button>
            <el-button v-if="!rangeMode" type="danger" plain :loading="analyzing" @click="enableByAnnotation">按标注启停</el-button>
          </template>
        </div>
        <div v-if="canEdit" class="toolbar-right">
          <span v-if="changes.length">{{ changes.length }} 项待保存</span>
          <el-button data-test="save-changes" type="primary" :loading="saving" :disabled="!changes.length" @click="saveChanges">保存更改</el-button>
        </div>
      </section>

      <section class="frames-stats" aria-label="采样帧统计">
        <article class="stats-cluster">
          <span class="stats-title">帧状态</span>
          <div data-test="total-count"><span>采样帧</span><strong>{{ frames.length }}</strong></div>
          <div><span>启用</span><strong class="enabled-text">{{ enabledCount }}</strong></div>
          <div><span>停用</span><strong class="disabled-text">{{ disabledCount }}</strong></div>
        </article>
        <article class="stats-cluster">
          <span class="stats-title">标注覆盖</span>
          <div data-test="annotated-count"><span>包含标注</span><strong>{{ annotatedIds.size }}</strong></div>
          <div data-test="annotated-enabled-count"><span>已启用</span><strong class="enabled-text">{{ annotatedEnabledCount }}</strong></div>
          <div data-test="annotated-disabled-count"><span>已停用</span><strong class="disabled-text">{{ annotatedDisabledCount }}</strong></div>
        </article>
        <article v-if="rangeMode || canEdit" class="stats-cluster stats-actions">
          <span class="stats-title">当前操作</span>
          <div v-if="rangeMode"><span>已选</span><strong>{{ selected.size }}</strong></div>
          <div v-if="canEdit" data-test="pending-count"><span>待保存</span><strong class="pending-text">{{ changes.length }}</strong></div>
        </article>
      </section>

      <section v-loading="loading" class="frames-grid-shell">
        <el-alert v-if="error" class="frames-error" :title="error" type="error" show-icon @close="error = ''" />
        <div v-if="!loading && !frames.length" class="empty-state">该视频尚无采样帧</div>
        <div class="frames-grid">
          <article
            v-for="frame in visibleFrames"
            :key="frame.id"
            data-test="frame-card"
            class="frame-card"
            :class="{ disabled: !draft[frame.id], selected: selected.has(frame.id) }"
          >
            <button
              type="button"
              class="frame-thumb"
              :aria-pressed="rangeMode ? selected.has(frame.id) : undefined"
              :title="rangeMode ? `选择第 ${frame.sequence} 帧` : `查看第 ${frame.sequence} 帧大图`"
              @click="handleThumbnail(frame, $event)"
            >
              <FrameAnnotationThumbnail
                :image-url="frameImageUrl(projectId, videoId, frame.id)"
                :image-width="imageWidth"
                :image-height="imageHeight"
                :annotations="showThumbnailAnnotations ? (frame.annotations ?? []) : []"
                :label-colors="labelColors"
                :sequence="frame.sequence"
                :time-offset="frame.time_offset"
                :disabled="!draft[frame.id]"
              />
              <span v-if="rangeMode" class="selection-box"><span v-if="selected.has(frame.id)">✓</span></span>
            </button>
            <footer>
              <span :title="frameFileName(frame)">{{ frameFileName(frame) }}</span>
              <button
                v-if="canEdit"
                :data-test="`toggle-${frame.id}`"
                type="button"
                :class="draft[frame.id] ? 'disable-button' : 'enable-button'"
                @click="toggleDraft(frame.id)"
              >{{ draft[frame.id] ? '停用' : '启用' }}</button>
            </footer>
          </article>
        </div>
      </section>

      <footer class="frames-pagination">
        <el-pagination
          v-if="pageSize !== 'all' && totalPages > 1"
          v-model:current-page="page"
          background
          layout="prev, pager, next"
          :page-size="pageSize"
          :total="frames.length"
        />
        <span>{{ pageSize === 'all' ? `全部 ${frames.length} 帧` : `第 ${page} / ${totalPages} 页 · 共 ${frames.length} 帧` }}</span>
      </footer>
    </main>

    <el-dialog v-model="patternOpen" append-to-body width="520px" title="启停模板" class="frame-pattern-dialog">
      <div class="pattern-form">
        <label><span>模板长度</span><el-input-number v-model="patternLength" :min="2" :max="8" /></label>
        <div class="pattern-row">
          <span>启停序列</span>
          <div>
            <button
              v-for="(_, index) in pattern"
              :key="index"
              type="button"
              :class="pattern[index] ? 'pattern-enabled' : 'pattern-disabled'"
              @click="togglePattern(index)"
            >{{ pattern[index] ? '启用' : '停用' }}</button>
          </div>
        </div>
        <el-alert title="仅修改前端状态，需点击“保存更改”才会写入数据库。" type="warning" :closable="false" show-icon />
      </div>
      <template #footer>
        <el-button @click="patternOpen = false">取消</el-button>
        <el-button type="primary" :disabled="rangeMode && !selected.size" @click="applyPattern">
          {{ rangeMode ? `应用到选中的 ${selected.size} 帧` : `应用到全部 ${frames.length} 帧` }}
        </el-button>
      </template>
    </el-dialog>

    <Transition name="preview-fade">
      <section v-if="previewFrame" data-test="frame-preview" class="frame-preview" @wheel="handlePreviewWheel">
        <header>
          <div class="preview-info">
            <strong>#{{ previewFrame.sequence }} · {{ previewFileName }}</strong>
            <span>{{ formatFrameTimestamp(previewFrame.time_offset) }}</span>
            <span>{{ imageWidth }} × {{ imageHeight }}</span>
            <span>{{ formatFileSize(previewFrame.file_size) }}</span>
            <b :class="draft[previewFrame.id] ? 'enabled-status' : 'disabled-status'">{{ draft[previewFrame.id] ? '已启用' : '已停用' }}</b>
          </div>
          <button type="button" title="关闭大图预览" aria-label="关闭大图预览" @click="closePreview"><el-icon><Close /></el-icon></button>
        </header>
        <div
          ref="previewStage"
          data-test="preview-stage"
          class="preview-stage"
          :class="{ dragging: previewDrag, pannable: previewZoom > 1 }"
          @pointerdown="startPreviewDrag"
          @pointermove="movePreviewDrag"
          @pointerup="stopPreviewDrag"
          @pointercancel="stopPreviewDrag"
        >
          <svg
            data-test="preview-image"
            class="preview-image"
            :class="{ 'boxes-hidden': !boxesVisible }"
            :style="previewTransform"
            :viewBox="`0 0 ${Math.max(1, imageWidth)} ${Math.max(1, imageHeight)}`"
            preserveAspectRatio="xMidYMid meet"
            role="img"
            :aria-label="`第 ${previewFrame.sequence} 帧大图`"
          >
            <image :href="frameImageUrl(projectId, videoId, previewFrame.id)" :width="Math.max(1, imageWidth)" :height="Math.max(1, imageHeight)" />
            <g v-if="boxesVisible" class="annotation-layer">
              <g v-for="(item, index) in previewAnnotations" :key="item.id">
                <rect
                  class="preview-annotation-box"
                  :x="item.x_min"
                  :y="item.y_min"
                  :width="Math.max(1, item.x_max - item.x_min)"
                  :height="Math.max(1, item.y_max - item.y_min)"
                  :stroke="labelColors[item.label_id] ?? '#ffca3a'"
                  :fill="colorWithAlpha(labelColors[item.label_id] ?? '#ffca3a', 0.12)"
                  vector-effect="non-scaling-stroke"
                />
                <g :transform="`translate(${item.x_min} ${item.y_min - annotationLabelSize(item, index).height})`">
                  <rect
                    class="preview-label-background"
                    :width="annotationLabelSize(item, index).width"
                    :height="annotationLabelSize(item, index).height"
                    :fill="labelColors[item.label_id] ?? '#ffca3a'"
                  />
                  <text
                    :x="annotationLabelSize(item, index).fontSize * 0.34"
                    :y="annotationLabelSize(item, index).fontSize"
                    :font-size="annotationLabelSize(item, index).fontSize"
                    font-weight="700"
                    :fill="contrastText(labelColors[item.label_id] ?? '#ffca3a')"
                  >{{ annotationTitle(item, index) }}</text>
                </g>
              </g>
            </g>
          </svg>
          <div v-if="previewLoading" class="preview-loading">正在加载标注信息…</div>
          <aside class="preview-minimap" data-test="preview-minimap">
            <header><strong>缩略图</strong><span>{{ Math.round(previewZoom * 100) }}%</span></header>
            <svg
              :viewBox="`0 0 ${Math.max(1, imageWidth)} ${Math.max(1, imageHeight)}`"
              preserveAspectRatio="xMidYMid meet"
              aria-label="当前大图视口位置"
            >
              <image :href="frameImageUrl(projectId, videoId, previewFrame.id)" :width="Math.max(1, imageWidth)" :height="Math.max(1, imageHeight)" />
              <rect
                class="preview-viewport-box"
                :x="previewViewport.x_min"
                :y="previewViewport.y_min"
                :width="Math.max(0, previewViewport.x_max - previewViewport.x_min)"
                :height="Math.max(0, previewViewport.y_max - previewViewport.y_min)"
                vector-effect="non-scaling-stroke"
              />
            </svg>
          </aside>
        </div>
        <footer>
          <el-button v-if="canEdit" data-test="preview-toggle-enabled" :type="draft[previewFrame.id] ? 'danger' : 'success'" @click="toggleDraft(previewFrame.id)">{{ draft[previewFrame.id] ? '停用采样帧' : '启用采样帧' }} · S</el-button>
          <el-button :disabled="previewIndex === 0" @click="movePreview(-1)"><el-icon><ArrowLeftBold /></el-icon>上一张 · A</el-button>
          <el-button :disabled="previewIndex === frames.length - 1" @click="movePreview(1)">下一张 · D<el-icon><ArrowRightBold /></el-icon></el-button>
          <el-button title="缩小" @click="zoomPreview(-0.1)"><el-icon><ZoomOut /></el-icon></el-button>
          <span>{{ Math.round(previewZoom * 100) }}%</span>
          <el-button data-test="preview-zoom-in" title="放大" @click="zoomPreview(0.1)"><el-icon><ZoomIn /></el-icon></el-button>
          <el-button @click="resetPreviewView"><el-icon><Refresh /></el-icon>重置 · R</el-button>
          <el-button @click="boxesVisible = !boxesVisible"><el-icon><Hide v-if="boxesVisible" /><View v-else /></el-icon>{{ boxesVisible ? '隐藏标注框' : '显示标注框' }} · H</el-button>
        </footer>
      </section>
    </Transition>
  </el-dialog>
</template>

<style scoped>
.focus-header,
.focus-title,
.frames-toolbar,
.toolbar-left,
.toolbar-right,
.frames-stats,
.frame-card footer,
.frame-preview > header,
.preview-info,
.frame-preview > footer { display: flex; align-items: center; }

.focus-header { justify-content: space-between; height: 52px; padding: 0 14px; color: #dce5eb; background: #17212b; border-bottom: 1px solid #3a4a56; }
.focus-title { gap: 12px; min-width: 0; }
.focus-title > span { color: var(--vdw-mint); font: 700 13px var(--vdw-mono); letter-spacing: .12em; }
.focus-title strong { max-width: 58vw; overflow: hidden; font: 650 16px var(--vdw-title); text-overflow: ellipsis; white-space: nowrap; }
.focus-title code { color: #92a2ae; font: 12px var(--vdw-mono); }
.focus-header > button,
.frame-preview > header > button { display: grid; place-items: center; width: 34px; height: 34px; padding: 0; color: #d3dde3; background: #263641; border: 1px solid #41515d; border-radius: 3px; cursor: pointer; }

.frames-workbench { display: grid; grid-template-rows: 54px 42px minmax(0, 1fr) 47px; height: calc(100dvh - 52px); overflow: hidden; color: #dce5eb; background: #111820; }
.frames-toolbar { justify-content: space-between; gap: 16px; min-width: 0; padding: 0 14px; background: #1d2933; border-bottom: 1px solid #33414c; }
.toolbar-left,
.toolbar-right { gap: 8px; min-width: 0; white-space: nowrap; }
.toolbar-left { overflow-x: auto; scrollbar-width: none; }
.toolbar-left::-webkit-scrollbar { display: none; }
.toolbar-left label { display: flex; align-items: center; gap: 7px; color: #aebbc4; font-size: 12px; }
.page-size-select { width: 92px; }
.toolbar-right span { color: #f3c76d; font: 12px var(--vdw-mono); }
.frames-toolbar :deep(.el-button) { height: 30px; padding: 0 11px; color: #dce5eb; background: #263641; border-color: #41515d; border-radius: 3px; }
.frames-toolbar :deep(.el-button:hover:not(:disabled)) { color: #9de0cc; background: #2d414b; border-color: #507165; }
.frames-toolbar :deep(.el-button--primary) { color: white; background: #16866f; border-color: #16866f; }
.frames-toolbar :deep(.el-button--danger) { color: #ffcaca; background: #40282d; border-color: #7e4347; }
.frames-toolbar :deep(.el-button--success) { color: #dff8ef; background: #244d43; border-color: #397261; }
.page-size-select :deep(.el-select__wrapper) { min-height: 30px; color: #dce5eb; background: #263641; box-shadow: 0 0 0 1px #41515d inset; }

.frames-stats { gap: 30px; min-width: 0; overflow-x: auto; padding: 0 16px; white-space: nowrap; background: #18232c; border-bottom: 1px solid #2e3d47; scrollbar-width: none; }
.frames-stats::-webkit-scrollbar { display: none; }
.stats-cluster { display: flex; align-items: center; align-self: stretch; gap: 17px; min-width: max-content; padding-right: 30px; border-right: 1px solid #34434e; }
.stats-cluster:last-child { border-right: 0; }
.stats-cluster > div { display: flex; align-items: center; gap: 8px; height: 100%; }
.stats-cluster > div span { color: #96a5af; font-size: 12px; }
.stats-cluster strong { font: 700 16px var(--vdw-mono); line-height: 1; }
.stats-title { color: #6f808b; font: 700 11px var(--vdw-mono); letter-spacing: .08em; }
.stats-actions { margin-left: auto; }
.enabled-text { color: #78d2b8; }.disabled-text { color: #ff8a8a; }.pending-text { color: #f3c76d; }

.frames-grid-shell { position: relative; min-height: 0; overflow: auto; padding: 12px 14px 18px; scrollbar-color: #16866f #0b1117; scrollbar-width: thin; }
.frames-grid-shell::-webkit-scrollbar { width: 10px; }.frames-grid-shell::-webkit-scrollbar-track { background: #0b1117; }.frames-grid-shell::-webkit-scrollbar-thumb { background: #16866f; border: 2px solid #0b1117; border-radius: 6px; }
.frames-error { position: sticky; z-index: 8; top: 0; margin-bottom: 10px; }
.frames-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(166px, 1fr)); gap: 9px; align-content: start; }
.frame-card { min-width: 0; overflow: hidden; background: #1b252e; border: 1px solid #34434e; border-radius: 3px; transition: border-color 150ms ease, box-shadow 150ms ease; }
.frame-card:hover { border-color: #567063; box-shadow: 0 6px 18px rgb(0 0 0 / 24%); }
.frame-card.selected { border-color: #78d2b8; box-shadow: 0 0 0 1px #16866f; }
.frame-thumb { position: relative; display: block; width: 100%; aspect-ratio: 16 / 9; overflow: hidden; padding: 0; color: inherit; background: #111820; border: 0; cursor: pointer; }
.selection-box { position: absolute; z-index: 4; top: 6px; left: 6px; display: grid; place-items: center; width: 22px; height: 22px; padding: 0; color: white; font: 10px var(--vdw-mono); background: #17212b; border: 1px solid #7b8a94; border-radius: 2px; }
.selected .selection-box { background: #16866f; border-color: #78d2b8; }
.frame-card footer { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; min-height: 52px; padding: 6px 7px 6px 10px; border-top: 1px solid #34434e; }
.frame-card footer > span { display: -webkit-box; overflow: hidden; color: #c6d1d8; font: 11px/15px var(--vdw-mono); overflow-wrap: anywhere; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.frame-card footer button { min-width: 52px; height: 29px; padding: 0 10px; color: white; border-radius: 3px; cursor: pointer; }
.disable-button { background: #6a3034; border: 1px solid #95464d; }.enable-button { background: #245a4c; border: 1px solid #397a68; }
.empty-state { display: grid; min-height: 240px; place-items: center; color: #8797a2; }
.range-mode { user-select: none; }

.frames-pagination { display: flex; align-items: center; justify-content: center; gap: 12px; background: #17212b; border-top: 1px solid #33414c; }
.frames-pagination > span { color: #8797a2; font: 11px var(--vdw-mono); }
.frames-pagination :deep(.el-pagination) { --el-pagination-bg-color: #263641; --el-pagination-button-color: #b9c6cf; --el-pagination-hover-color: #78d2b8; }
.frames-pagination :deep(.el-pager li),
.frames-pagination :deep(.btn-prev),
.frames-pagination :deep(.btn-next) { color: #b9c6cf; background: #263641; border: 1px solid #354752; border-radius: 3px; }
.frames-pagination :deep(.el-pager li.is-active) { color: white; background: #16866f; border-color: #16866f; }

.pattern-form { display: grid; gap: 18px; }.pattern-form > label { display: grid; grid-template-columns: 92px minmax(0, 1fr); align-items: center; }.pattern-form label > span,
.pattern-row > span { color: #687482; font-size: 13px; }.pattern-row { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 12px; }.pattern-row > div { display: flex; flex-wrap: wrap; gap: 7px; }
.pattern-row button { min-width: 54px; height: 32px; color: white; border-radius: 3px; cursor: pointer; }.pattern-enabled { background: #16866f; border: 1px solid #0f705d; }.pattern-disabled { background: #c83f49; border: 1px solid #a9343d; }

.frame-preview { position: fixed; inset: 0; z-index: 3100; display: grid; grid-template-rows: 54px minmax(0, 1fr) 62px; color: #dce5eb; background: rgb(2 6 9 / 80%); }
.frame-preview > header { justify-content: space-between; gap: 18px; padding: 0 18px; background: rgb(23 33 43 / 94%); border-bottom: 1px solid #40505c; }
.preview-info { gap: 14px; min-width: 0; }.preview-info strong { overflow: hidden; font: 650 15px var(--vdw-title); text-overflow: ellipsis; white-space: nowrap; }.preview-info span { color: #99a9b4; font: 12px var(--vdw-mono); white-space: nowrap; }.preview-info b { padding: 3px 7px; font-size: 11px; border-radius: 2px; white-space: nowrap; }.enabled-status { color: #dff8ef; background: #245a4c; }.disabled-status { color: white; background: #c83f49; }
.preview-stage { position: relative; min-height: 0; overflow: hidden; background: rgb(2 6 9 / 22%); cursor: default; touch-action: none; }
.preview-stage.pannable { cursor: grab; }
.preview-stage.dragging { cursor: grabbing; }
.preview-image { position: absolute; top: 0; left: 0; display: block; max-width: none; max-height: none; overflow: visible; background: rgb(17 24 32 / 55%); box-shadow: 0 12px 40px rgb(0 0 0 / 70%); transform-origin: 0 0; transition: transform 120ms ease; will-change: transform; }
.preview-stage.dragging .preview-image { transition: none; }
.preview-annotation-box { stroke-width: 3px; }
.preview-label-background { stroke: none; }
.preview-loading { position: absolute; z-index: 4; top: 50%; left: 50%; padding: 8px 12px; color: #c9d4da; background: rgb(14 22 28 / 72%); transform: translate(-50%, -50%); }
.preview-minimap { position: absolute; z-index: 5; right: 14px; bottom: 14px; width: 240px; padding: 8px; color: #24313a; background: rgb(246 248 249 / 88%); border: 1px solid #70818c; box-shadow: 0 8px 24px rgb(0 0 0 / 38%); backdrop-filter: blur(5px); }
.preview-minimap header { display: flex; align-items: center; justify-content: space-between; height: 24px; }
.preview-minimap header strong { font-size: 12px; }.preview-minimap header span { color: #687782; font: 11px var(--vdw-mono); }
.preview-minimap svg { display: block; width: 100%; aspect-ratio: 16 / 9; background: #17212b; }
.preview-viewport-box { fill: rgb(120 210 184 / 10%); stroke: #78d2b8; stroke-width: 2px; filter: drop-shadow(0 0 1px rgb(23 33 43 / 80%)); }
.frame-preview > footer { justify-content: center; gap: 8px; padding: 0 14px; overflow-x: auto; white-space: nowrap; background: rgb(23 33 43 / 94%); border-top: 1px solid #40505c; }.frame-preview > footer > span { color: #9eafb9; font: 12px var(--vdw-mono); }
.frame-preview > footer :deep(.el-button) { height: 31px; padding: 0 11px; color: #dce5eb; background: #263641; border-color: #41515d; border-radius: 3px; }
.frame-preview > footer :deep(.el-button:hover:not(:disabled)) { color: #9de0cc; background: #2d414b; border-color: #507165; }
.frame-preview > footer :deep(.el-button--danger) { color: #ffcaca; background: #6a3034; border-color: #95464d; }
.frame-preview > footer :deep(.el-button--success) { color: #dff8ef; background: #245a4c; border-color: #397a68; }
.preview-fade-enter-active,
.preview-fade-leave-active { transition: opacity 180ms ease; }.preview-fade-enter-from,
.preview-fade-leave-to { opacity: 0; }

@media (hover: hover) {
  .frames-workbench :deep(.el-button:not(.is-disabled):not(.is-text):not(.is-link):hover),
  .frames-workbench :deep(.el-button:not(.is-disabled):not(.is-text):not(.is-link):active),
  .frame-preview :deep(.el-button:not(.is-disabled):not(.is-text):not(.is-link):hover),
  .frame-preview :deep(.el-button:not(.is-disabled):not(.is-text):not(.is-link):active) { transform: none; }
}

@media (max-width: 1100px) {
  .frames-grid { grid-template-columns: repeat(auto-fill, minmax(154px, 1fr)); }
  .frames-stats { gap: 18px; }.stats-cluster { gap: 12px; padding-right: 18px; }
  .preview-info span:nth-of-type(2),
  .preview-info span:nth-of-type(3) { display: none; }
  .preview-minimap { width: 190px; }
}

@media (prefers-reduced-motion: reduce) {
  .frame-card,
  .preview-image,
  .preview-fade-enter-active,
  .preview-fade-leave-active { transition: none; }
}
</style>

<style>
.frames-workbench-dialog { margin: 0 !important; padding: 0 !important; background: #111820 !important; }
.frames-workbench-dialog > .el-dialog__header { height: 52px; padding: 0 !important; margin: 0 !important; }
.frames-workbench-dialog > .el-dialog__body { height: calc(100dvh - 52px); padding: 0 !important; overflow: hidden; }
.frame-filter-confirm { border: 1px solid #9ba9b2; box-shadow: 0 20px 60px rgb(0 0 0 / 45%); }
.frame-pattern-dialog { border: 1px solid #9ba9b2; }
</style>
