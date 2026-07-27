<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  getFrameAnnotations,
  replaceFrameAnnotations,
  type FrameAnnotation,
  type FrameAnnotationSet,
} from '../api/annotations'
import { getCurrentUser, type CurrentUser } from '../api/auth'
import { getCapabilities, type SystemCapabilities } from '../api/capabilities'
import { listLabels, type ProjectLabel } from '../api/labels'
import {
  frameImageUrl,
  listFrames,
  listVideos,
  setFramesEnabled,
  type Frame,
  type SamplingSummary,
  type ProjectTask,
  type Video,
} from '../api/media'
import {
  createBatchAutoAnnotation,
  listInferenceModels,
  registerInferenceModel,
  runFrameAutoAnnotation,
  type AutoAnnotationConfig,
  type InferenceModel,
} from '../api/models'
import { getProject } from '../api/projects'
import AnnotationCanvas from '../components/AnnotationCanvas.vue'
import ServerVideoPicker from '../components/ServerVideoPicker.vue'
import { type BoxBounds, type Point } from './annotationGeometry'
import { createAnnotationHistory } from './annotationHistory'

type CanvasMode = 'select' | 'draw' | 'pan'
type CanvasApi = { zoomBy: (factor: number) => void; resetView: () => void; zoomPercent: number }

const route = useRoute()
const router = useRouter()
const projectId = String(route.params.id)
const videoId = String(route.params.videoId)
const canvasRef = ref<CanvasApi | null>(null)
const workbenchRoot = ref<HTMLElement | null>(null)
const video = ref<Video | null>(null)
const frames = ref<Frame[]>([])
const labels = ref<ProjectLabel[]>([])
const inferenceModels = ref<InferenceModel[]>([])
const capabilities = ref<SystemCapabilities | null>(null)
const currentUser = ref<CurrentUser | null>(null)
const sampling = ref<SamplingSummary | null>(null)
const currentIndex = ref(0)
const annotations = ref<FrameAnnotation[]>([])
const annotationRevision = ref(1)
const selectedId = ref<string | null>(null)
const mode = ref<CanvasMode>('select')
const dirty = ref(false)
const loading = ref(true)
const loadingFrame = ref(false)
const saving = ref(false)
const error = ref('')
const saveText = ref('已同步')
const hiddenLabelIds = ref<string[]>([])
const expandedLabelIds = ref<string[]>([])
const crosshair = ref(false)
const overwrite = ref(false)
const gridOpen = ref(false)
const shortcutsOpen = ref(false)
const statsOpen = ref(false)
const registerOpen = ref(false)
const registering = ref(false)
const registerName = ref('')
const registerKind = ref<InferenceModel['kind']>('yolo')
const registerPath = ref('')
const inferenceRunning = ref(false)
const activeAutoTask = ref<ProjectTask | null>(null)
const pendingBounds = ref<BoxBounds | null>(null)
const pendingAnchor = ref<Point>({ x: 24, y: 24 })
const lastLabelId = ref('')
const viewport = ref<BoxBounds | null>(null)
const autoModel = ref('')
const autoCategories = ref<string[]>(['__all__'])
const confidence = ref(0.25)
const iou = ref(0.45)
const cache = new Map<string, FrameAnnotationSet>()
let history = createAnnotationHistory([])
let spaceHeld = false
let modeBeforeSpace: CanvasMode = 'select'
let taskTimer: ReturnType<typeof setInterval> | undefined

const currentFrame = computed(() => frames.value[currentIndex.value] ?? null)
const imageUrl = computed(() =>
  currentFrame.value
    ? frameImageUrl(projectId, videoId, currentFrame.value.id)
    : '',
)
const frameFileName = computed(() => {
  const sequence = currentFrame.value?.sequence ?? 0
  const extension = sampling.value?.output_format ?? 'jpg'
  return `${String(sequence).padStart(6, '0')}.${extension}`
})
const enabledLabels = computed(() => labels.value.filter((label) => label.enabled))
const readyModels = computed(() => inferenceModels.value.filter((model) => {
  if (model.status !== 'ready') return false
  const feature = model.kind === 'yolo'
    ? capabilities.value?.features.yolo_auto_annotation
    : capabilities.value?.features.grounding_dino_auto_annotation
  return feature?.available === true
}))
const selectedModel = computed(() =>
  inferenceModels.value.find((model) => model.id === autoModel.value) ?? null,
)
const batchActive = computed(() =>
  activeAutoTask.value?.type === 'auto_annotate'
  && ['queued', 'running'].includes(activeAutoTask.value.status),
)
const autoUnavailableReason = computed(() => {
  if (readyModels.value.length) return ''
  return capabilities.value?.features.yolo_auto_annotation.reason
    ?? capabilities.value?.features.grounding_dino_auto_annotation.reason
    ?? '没有可用的已入库模型'
})
const autoUnavailableText = computed(() => {
  const yolo = capabilities.value?.features.yolo_auto_annotation.available
  const dino = capabilities.value?.features.grounding_dino_auto_annotation.available
  return yolo === false && dino === false ? 'GPU功能不可用' : '暂无可用模型'
})
const groupedObjects = computed(() => labels.value
  .map((label) => ({
    label,
    items: annotations.value.filter((item) => item.label_id === label.id),
  }))
  .filter((group) => group.items.length > 0))
const allBoxesHidden = computed(() =>
  groupedObjects.value.length > 0
  && groupedObjects.value.every(({ label }) => hiddenLabelIds.value.includes(label.id)),
)
const minimapRect = computed(() => {
  if (!viewport.value || !video.value?.width || !video.value.height) return null
  const left = Math.max(0, Math.min(100, viewport.value.x_min / video.value.width * 100))
  const top = Math.max(0, Math.min(100, viewport.value.y_min / video.value.height * 100))
  const right = Math.max(left, Math.min(100, viewport.value.x_max / video.value.width * 100))
  const bottom = Math.max(top, Math.min(100, viewport.value.y_max / video.value.height * 100))
  return { left: `${left}%`, top: `${top}%`, width: `${right - left}%`, height: `${bottom - top}%` }
})
const enabledFrameCount = computed(() => frames.value.filter((frame) => frame.enabled).length)
const boxCount = computed(() => annotations.value.length)

function clone(items: FrameAnnotation[]) {
  return items.map((item) => ({ ...item }))
}

function syncHistoryState() {
  saveText.value = dirty.value ? '未保存' : '已同步'
}

function pushDraft(items: FrameAnnotation[]) {
  if (batchActive.value) return
  annotations.value = clone(items)
  history.push(items)
  dirty.value = true
  syncHistoryState()
}

function undo() {
  const value = history.undo()
  if (!value) return
  annotations.value = value
  dirty.value = true
  syncHistoryState()
}

function redo() {
  const value = history.redo()
  if (!value) return
  annotations.value = value
  dirty.value = true
  syncHistoryState()
}

function deleteSelected() {
  if (!selectedId.value) return
  pushDraft(annotations.value.filter((item) => item.id !== selectedId.value))
  selectedId.value = null
}

function clearAll() {
  if (!annotations.value.length) return
  pushDraft([])
  selectedId.value = null
}

function requestCategory(bounds: BoxBounds, anchor: Point) {
  pendingBounds.value = bounds
  pendingAnchor.value = anchor
  if (!lastLabelId.value) lastLabelId.value = enabledLabels.value[0]?.id ?? ''
}

function confirmCategory() {
  if (!pendingBounds.value || !lastLabelId.value) return
  const item: FrameAnnotation = {
    id: crypto.randomUUID(),
    label_id: lastLabelId.value,
    ...pendingBounds.value,
    source: 'manual',
    confidence: null,
  }
  pushDraft([...annotations.value, item])
  selectedId.value = item.id
  pendingBounds.value = null
  mode.value = 'select'
}

function cancelCategory() {
  pendingBounds.value = null
  mode.value = 'select'
}

async function saveCurrent() {
  const frame = currentFrame.value
  if (!frame || !dirty.value) return true
  saving.value = true
  saveText.value = '保存中…'
  try {
    const saved = await replaceFrameAnnotations(projectId, videoId, {
      frame_id: frame.id,
      annotation_revision: annotationRevision.value,
      items: clone(annotations.value),
    })
    annotations.value = clone(saved.items)
    annotationRevision.value = saved.annotation_revision
    cache.set(frame.id, { ...saved, items: clone(saved.items) })
    dirty.value = false
    saveText.value = '已同步'
    return true
  } catch (reason) {
    saveText.value = '保存失败'
    ElMessage.error(reason instanceof Error ? reason.message : '标注保存失败')
    return false
  } finally {
    saving.value = false
  }
}

function autoConfig(): AutoAnnotationConfig | null {
  if (!selectedModel.value) {
    ElMessage.warning('请先选择可用模型。')
    return null
  }
  const categories = autoCategories.value.includes('__all__')
    ? []
    : [...new Set(autoCategories.value.map((item) => item.trim().toLowerCase()).filter(Boolean))]
  return {
    model_id: selectedModel.value.id,
    categories,
    confidence: confidence.value,
    iou: iou.value,
  }
}

async function runSingleAutoAnnotation() {
  const frame = currentFrame.value
  const config = autoConfig()
  if (!frame || !config || batchActive.value) return
  inferenceRunning.value = true
  try {
    const result = await runFrameAutoAnnotation(
      projectId, videoId, frame.id, config,
    )
    if (result.created_labels.length) {
      labels.value = [...labels.value, ...result.created_labels]
        .sort((left, right) => left.sort_order - right.sort_order)
    }
    const inferred = result.items.map(({ label_name: _labelName, ...item }) => item)
    pushDraft(overwrite.value ? inferred : [...annotations.value, ...inferred])
    ElMessage.success(`单张自动标注完成，识别 ${inferred.length} 个对象。`)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '单张自动标注失败')
  } finally {
    inferenceRunning.value = false
  }
}

async function runBatchAutoAnnotation() {
  const config = autoConfig()
  if (video.value && !video.value.enabled) {
    ElMessage.warning('该视频已停用，请先在视频资料库启用后再运行批量自动标注。')
    return
  }
  if (!config || batchActive.value || !await saveCurrent()) return
  inferenceRunning.value = true
  try {
    activeAutoTask.value = await createBatchAutoAnnotation(
      projectId, videoId, config, overwrite.value,
    )
    ElMessage.success('批量自动标注任务已创建。')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '批量自动标注任务创建失败')
  } finally {
    inferenceRunning.value = false
  }
}

async function submitModelRegistration() {
  if (!registerName.value.trim() || !registerPath.value) return
  registering.value = true
  try {
    const registered = await registerInferenceModel(
      projectId,
      registerName.value,
      registerKind.value,
      registerPath.value,
    )
    inferenceModels.value = [registered.model, ...inferenceModels.value]
    registerOpen.value = false
    registerName.value = ''
    registerPath.value = ''
    ElMessage.success('模型入库任务已创建，可在任务中心查看进度。')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '模型登记失败')
  } finally {
    registering.value = false
  }
}

async function refreshAutoTask() {
  if (!video.value) return
  if (!batchActive.value && !inferenceModels.value.some((model) => model.status === 'copying')) return
  try {
    const page = await listVideos(projectId, 1, 999)
    const refreshed = page.items.find((item) => item.id === videoId)
    if (!refreshed) return
    const wasActive = batchActive.value
    video.value = refreshed
    activeAutoTask.value = refreshed.latest_task?.type === 'auto_annotate'
      ? refreshed.latest_task
      : null
    if (wasActive && !batchActive.value) {
      cache.clear()
      labels.value = await listLabels(projectId)
      await loadFrame(currentIndex.value)
      window.dispatchEvent(new CustomEvent('vdm:tasks-settled'))
    }
    if (inferenceModels.value.some((model) => model.status === 'copying')) {
      inferenceModels.value = await listInferenceModels()
      if (!autoModel.value) autoModel.value = readyModels.value[0]?.id ?? ''
    }
  } catch {
    // The task center remains the authoritative error surface for polling failures.
  }
}

async function loadFrame(index: number) {
  const frame = frames.value[index]
  if (!frame) return
  loadingFrame.value = true
  try {
    const value = cache.get(frame.id)
      ?? await getFrameAnnotations(projectId, videoId, frame.id)
    cache.set(frame.id, { ...value, items: clone(value.items) })
    currentIndex.value = index
    annotations.value = clone(value.items)
    annotationRevision.value = value.annotation_revision
    selectedId.value = null
    hiddenLabelIds.value = []
    pendingBounds.value = null
    history = createAnnotationHistory(value.items)
    dirty.value = false
    saveText.value = '已同步'
    canvasRef.value?.resetView()
    void nextTick(() => {
      workbenchRoot.value
        ?.querySelector<HTMLElement>('.film-frame.current')
        ?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest', inline: 'center' })
    })
    for (const neighbor of [frames.value[index - 1], frames.value[index + 1]]) {
      if (neighbor) new Image().src = frameImageUrl(projectId, videoId, neighbor.id)
    }
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '采样帧标注加载失败')
  } finally {
    loadingFrame.value = false
  }
}

async function switchFrame(index: number) {
  if (index === currentIndex.value || saving.value || loadingFrame.value) return
  if (!await saveCurrent()) return
  await loadFrame(index)
}

async function closeWorkbench() {
  if (!await saveCurrent()) return
  await router.push(`/projects/${projectId}/videos`)
}

async function toggleFrameEnabled(value: boolean | string | number) {
  const frame = currentFrame.value
  if (!frame || !sampling.value) return
  try {
    sampling.value = await setFramesEnabled(
      projectId,
      videoId,
      Boolean(value),
      [frame.id],
      sampling.value.frame_revision,
    )
    frame.enabled = Boolean(value)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '采样帧状态保存失败')
  }
}

function toggleLabelHidden(labelId: string) {
  hiddenLabelIds.value = hiddenLabelIds.value.includes(labelId)
    ? hiddenLabelIds.value.filter((id) => id !== labelId)
    : [...hiddenLabelIds.value, labelId]
}

function toggleAllBoxes() {
  hiddenLabelIds.value = allBoxesHidden.value
    ? []
    : groupedObjects.value.map(({ label }) => label.id)
}

function toggleExpanded(labelId: string) {
  expandedLabelIds.value = expandedLabelIds.value.includes(labelId)
    ? expandedLabelIds.value.filter((id) => id !== labelId)
    : [...expandedLabelIds.value, labelId]
}

function isInputTarget(target: EventTarget | null) {
  const element = target as HTMLElement | null
  return Boolean(element?.isContentEditable || ['INPUT', 'SELECT', 'TEXTAREA'].includes(element?.tagName ?? ''))
}

function handleKeyDown(event: KeyboardEvent) {
  if (event.code === 'Space' && !isInputTarget(event.target)) {
    event.preventDefault()
    if (!spaceHeld) {
      spaceHeld = true
      modeBeforeSpace = mode.value
      mode.value = 'pan'
    }
    return
  }
  if (isInputTarget(event.target) || event.repeat || pendingBounds.value) return
  if (batchActive.value && ['r', 'delete', 'z'].includes(event.key.toLowerCase())) return
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
    event.preventDefault()
    event.shiftKey ? redo() : undo()
    return
  }
  if (event.key.toLowerCase() === 'a') void switchFrame(currentIndex.value - 1)
  else if (event.key.toLowerCase() === 'd') void switchFrame(currentIndex.value + 1)
  else if (event.key.toLowerCase() === 'r') mode.value = 'draw'
  else if (event.key === 'Delete') deleteSelected()
}

function handleKeyUp(event: KeyboardEvent) {
  if (event.code !== 'Space' || !spaceHeld) return
  spaceHeld = false
  mode.value = modeBeforeSpace
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

async function loadAllFrames() {
  const first = await listFrames(projectId, videoId, 1, 200)
  sampling.value = first.sampling
  const pages = Math.ceil(first.total / first.page_size)
  const rest = pages > 1
    ? await Promise.all(
        Array.from({ length: pages - 1 }, (_, index) =>
          listFrames(projectId, videoId, index + 2, first.page_size)),
      )
    : []
  frames.value = [first, ...rest].flatMap((page) => page.items)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [project, videos, projectLabels, models, detectedCapabilities, user] = await Promise.all([
      getProject(projectId),
      listVideos(projectId, 1, 999),
      listLabels(projectId),
      listInferenceModels(),
      getCapabilities(),
      getCurrentUser(),
    ])
    if (project.role === 'viewer') {
      ElMessage.warning('只读成员不能进入在线标注。')
      await router.replace(`/projects/${projectId}/videos`)
      return
    }
    video.value = videos.items.find((item) => item.id === videoId) ?? null
    if (!video.value) throw new Error('视频不存在或不可访问')
    labels.value = projectLabels
    inferenceModels.value = models
    capabilities.value = detectedCapabilities
    currentUser.value = user
    activeAutoTask.value = video.value.latest_task?.type === 'auto_annotate'
      ? video.value.latest_task
      : null
    autoModel.value = models.find((model) => {
      if (model.status !== 'ready') return false
      return model.kind === 'yolo'
        ? detectedCapabilities.features.yolo_auto_annotation.available
        : detectedCapabilities.features.grounding_dino_auto_annotation.available
    })?.id ?? ''
    lastLabelId.value = projectLabels.find((label) => label.enabled)?.id ?? ''
    await loadAllFrames()
    if (!frames.value.length) throw new Error('该视频尚无采样帧')
    await loadFrame(0)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '标注工作台加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  window.addEventListener('keyup', handleKeyUp)
  window.addEventListener('beforeunload', handleBeforeUnload)
  taskTimer = setInterval(refreshAutoTask, 1500)
  void load()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('keyup', handleKeyUp)
  window.removeEventListener('beforeunload', handleBeforeUnload)
  if (taskTimer) clearInterval(taskTimer)
})
</script>

<template>
  <Teleport defer to="#focus-header-tools">
    <div class="annotation-focus-tools">
      <div class="focus-title">
        <strong :title="video?.title">{{ video?.title || '在线标注' }}</strong>
        <span data-test="frame-counter">{{ frames.length ? currentIndex + 1 : 0 }} / {{ frames.length }}</span>
      </div>
      <div class="focus-actions">
        <span class="save-state" :data-state="dirty ? 'dirty' : 'saved'">{{ batchActive ? `自动标注 ${activeAutoTask?.progress ?? 0}%` : saveText }}</span>
        <button type="button" data-test="close-annotation" title="保存并关闭" @click="closeWorkbench">关闭</button>
      </div>
    </div>
  </Teleport>

  <main ref="workbenchRoot" class="annotation-workbench" data-test="annotation-workbench">
    <section class="auto-bar" aria-label="自动标注控制">
      <div class="auto-controls">
        <el-select
          v-model="autoModel"
          class="model-select"
          placeholder="选择模型"
          :disabled="batchActive || inferenceRunning || !readyModels.length"
        >
          <el-option v-for="model in readyModels" :key="model.id" :label="model.name" :value="model.id" />
        </el-select>
        <button
          v-if="currentUser?.is_system_admin"
          type="button"
          :disabled="batchActive"
          title="登记本地推理模型"
          @click="registerOpen = true"
        >＋模型</button>
        <el-select
          v-model="autoCategories"
          class="category-select"
          multiple
          filterable
          allow-create
          default-first-option
          collapse-tags
          placeholder="类别"
          :disabled="batchActive || inferenceRunning || !autoModel"
        >
          <el-option label="All / 全类别" value="__all__" />
          <el-option v-for="label in enabledLabels" :key="label.id" :label="label.name" :value="label.name" />
        </el-select>
        <label>置信度 <el-input-number v-model="confidence" :min="0" :max="1" :step="0.05" :precision="2" :disabled="batchActive || inferenceRunning" /></label>
        <label>IoU <el-input-number v-model="iou" :min="0" :max="1" :step="0.05" :precision="2" :disabled="batchActive || inferenceRunning" /></label>
        <button data-test="run-single-auto" type="button" :disabled="batchActive || inferenceRunning || !autoModel" @click="runSingleAutoAnnotation">单张运行</button>
        <button data-test="run-batch-auto" type="button" :disabled="batchActive || inferenceRunning || !autoModel || video?.enabled === false" @click="runBatchAutoAnnotation">批量运行</button>
        <span v-if="autoUnavailableReason" class="auto-warning" :title="autoUnavailableReason">{{ autoUnavailableText }}</span>
      </div>
      <div class="frame-controls">
        <label>启用帧 <el-switch :model-value="currentFrame?.enabled ?? false" :disabled="!currentFrame || batchActive" @change="toggleFrameEnabled" /></label>
        <button type="button" @click="statsOpen = true">标注统计</button>
        <label>标签覆盖 <el-switch v-model="overwrite" disabled /></label>
        <label>十字线 <el-switch v-model="crosshair" :disabled="batchActive" /></label>
      </div>
    </section>

    <aside class="tool-rail" aria-label="标注工具">
      <button :class="{ active: mode === 'pan' }" type="button" title="拖拽（按住 Space）" @click="mode = 'pan'">✥</button>
      <button data-test="previous-frame" type="button" title="上一张（A）" :disabled="currentIndex === 0" @click="switchFrame(currentIndex - 1)">A</button>
      <button data-test="next-frame" type="button" title="下一张（D）" :disabled="currentIndex >= frames.length - 1" @click="switchFrame(currentIndex + 1)">D</button>
      <button :class="{ active: mode === 'draw' }" type="button" title="新建矩形框（R）" :disabled="batchActive" @click="mode = 'draw'">R</button>
      <button type="button" title="隐藏/显示全部标注框" @click="toggleAllBoxes">◉</button>
      <button type="button" title="清空所有标注框" :disabled="batchActive || !annotations.length" @click="clearAll">⌫</button>
      <button type="button" title="撤销（Ctrl+Z）" :disabled="batchActive || !history.canUndo()" @click="undo">↶</button>
      <button type="button" title="重做（Ctrl+Shift+Z）" :disabled="batchActive || !history.canRedo()" @click="redo">↷</button>
      <span class="tool-separator" />
      <button type="button" title="展示全图" @click="canvasRef?.resetView()">▣</button>
      <button type="button" title="缩小" @click="canvasRef?.zoomBy(0.9)">−</button>
      <output>{{ canvasRef?.zoomPercent ?? 100 }}%</output>
      <button type="button" title="放大" @click="canvasRef?.zoomBy(1.1)">＋</button>
      <button type="button" title="快捷键指南" @click="shortcutsOpen = true">?</button>
    </aside>

    <section class="canvas-panel">
      <AnnotationCanvas
        v-if="video && currentFrame"
        ref="canvasRef"
        :image-url="imageUrl"
        :image-width="video.width"
        :image-height="video.height"
        :annotations="annotations"
        :labels="labels"
        :selected-id="selectedId"
        :mode="mode"
        :crosshair="crosshair"
        :hidden-label-ids="hiddenLabelIds"
        :readonly="batchActive"
        @change="pushDraft"
        @select="selectedId = $event"
        @request-category="requestCategory"
        @view-change="viewport = $event"
      />
      <div
        v-if="pendingBounds"
        class="category-picker"
        :style="{
          left: `clamp(130px, ${pendingAnchor.x}px, calc(100% - 130px))`,
          top: `clamp(8px, ${pendingAnchor.y}px, calc(100% - 82px))`,
        }"
      >
        <label>选择类别
          <select v-model="lastLabelId" autofocus>
            <option v-for="label in enabledLabels" :key="label.id" :value="label.id">{{ label.name }}</option>
          </select>
        </label>
        <button type="button" @click="confirmCategory">确认</button>
        <button type="button" @click="cancelCategory">取消</button>
      </div>
      <div v-if="loadingFrame" class="panel-overlay">正在载入采样帧…</div>
      <div v-else-if="batchActive" class="panel-overlay panel-overlay--passive">批量自动标注运行中 · 当前帧只读</div>
    </section>

    <aside class="info-panel">
      <section class="image-info">
        <header><strong>图像信息</strong><span>#{{ currentFrame?.sequence ?? 0 }}</span></header>
        <dl>
          <dt>文件名</dt><dd :title="frameFileName">{{ frameFileName }}</dd>
          <dt>尺寸</dt><dd>{{ video?.width ?? 0 }} × {{ video?.height ?? 0 }}</dd>
          <dt>大小</dt><dd>{{ ((currentFrame?.file_size ?? 0) / 1024).toFixed(1) }} KB</dd>
        </dl>
      </section>
      <section class="object-list">
        <header><strong>对象列表</strong><span>{{ boxCount }} 个</span></header>
        <p v-if="!groupedObjects.length" class="empty-copy">当前图像暂无标注框</p>
        <article v-for="group in groupedObjects" :key="group.label.id" class="object-group">
          <div class="object-group-row">
            <i :style="{ background: group.label.color }" />
            <button type="button" class="group-name" @click="toggleExpanded(group.label.id)">{{ group.label.name }}</button>
            <span>{{ group.items.length }}</span>
            <button type="button" :title="hiddenLabelIds.includes(group.label.id) ? '显示类别' : '隐藏类别'" @click="toggleLabelHidden(group.label.id)">{{ hiddenLabelIds.includes(group.label.id) ? '○' : '●' }}</button>
            <button type="button" title="展开/收起" @click="toggleExpanded(group.label.id)">{{ expandedLabelIds.includes(group.label.id) ? '⌃' : '⌄' }}</button>
          </div>
          <div v-if="expandedLabelIds.includes(group.label.id)" class="box-list">
            <button
              v-for="(item, index) in group.items"
              :key="item.id"
              type="button"
              :class="{ selected: selectedId === item.id }"
              @click="selectedId = item.id; mode = 'select'"
            >
              <span>#{{ index + 1 }}</span>
              <code>{{ item.x_min }},{{ item.y_min }} → {{ item.x_max }},{{ item.y_max }}</code>
            </button>
          </div>
        </article>
      </section>
      <section class="minimap">
        <header><strong>缩略图</strong><span>{{ canvasRef?.zoomPercent ?? 100 }}%</span></header>
        <div class="minimap-image">
          <img v-if="currentFrame" :src="imageUrl" alt="当前采样帧缩略图" />
          <span v-if="minimapRect" class="viewport-box" :style="minimapRect" />
        </div>
      </section>
    </aside>

    <section class="filmstrip">
      <div class="filmstrip-scroll">
        <button
          v-for="(frame, index) in frames"
          :key="frame.id"
          type="button"
          class="film-frame"
          :class="{ current: index === currentIndex, disabled: !frame.enabled }"
          :title="`第 ${frame.sequence} 帧`"
          @click="switchFrame(index)"
        >
          <img loading="lazy" :src="frameImageUrl(projectId, videoId, frame.id)" alt="" />
          <span>#{{ frame.sequence }}</span>
        </button>
      </div>
      <button class="expand-grid" type="button" title="展开全部采样帧" @click="gridOpen = true">⌃</button>
    </section>

    <section v-if="gridOpen" class="frame-grid-overlay" aria-label="全部采样帧">
      <header><strong>全部采样帧</strong><span>{{ enabledFrameCount }} / {{ frames.length }} 帧启用</span><button type="button" @click="gridOpen = false">关闭</button></header>
      <div class="frame-grid">
        <button v-for="(frame, index) in frames" :key="frame.id" type="button" :class="{ current: index === currentIndex, disabled: !frame.enabled }" @click="switchFrame(index).then(() => { gridOpen = false })">
          <img loading="lazy" :src="frameImageUrl(projectId, videoId, frame.id)" alt="" />
          <span>#{{ frame.sequence }} · {{ frame.time_offset.toFixed(2) }}s</span>
        </button>
      </div>
    </section>

    <div v-if="loading || error" class="workbench-state" :class="{ error: Boolean(error) }">
      <span>{{ error || '正在加载在线标注工作台…' }}</span>
      <button v-if="error" type="button" @click="closeWorkbench">返回原始数据</button>
    </div>
  </main>

  <el-dialog v-model="shortcutsOpen" title="快捷键操作指南" width="460px" append-to-body>
    <dl class="shortcut-list">
      <dt>A / D</dt><dd>上一张 / 下一张</dd><dt>R</dt><dd>新建矩形框</dd>
      <dt>Space</dt><dd>按住进入拖拽模式</dd><dt>Ctrl + 滚轮</dt><dd>缩放图像</dd>
      <dt>Ctrl + Z</dt><dd>撤销</dd><dt>Ctrl + Shift + Z</dt><dd>重做</dd>
      <dt>Delete</dt><dd>删除选中标注框</dd>
    </dl>
  </el-dialog>
  <el-dialog v-model="statsOpen" title="当前视频标注统计" width="520px" append-to-body>
    <div class="stats-summary"><strong>{{ frames.length }}</strong><span>采样帧</span><strong>{{ enabledFrameCount }}</strong><span>启用帧</span><strong>{{ boxCount }}</strong><span>当前帧标注框</span></div>
  </el-dialog>
  <el-dialog v-model="registerOpen" title="登记推理模型" width="min(760px, calc(100vw - 32px))" append-to-body>
    <div class="model-registration-form">
      <label><span>模型名称</span><el-input v-model="registerName" maxlength="128" placeholder="例如：安全帽 YOLO26 v1" /></label>
      <label><span>模型类型</span>
        <el-radio-group v-model="registerKind">
          <el-radio-button value="yolo">YOLO</el-radio-button>
          <el-radio-button value="grounding_dino">GroundingDINO</el-radio-button>
        </el-radio-group>
      </label>
      <p>{{ registerKind === 'yolo' ? '选择 .pt 或 .onnx 模型文件。' : '选择包含 Transformers 本地模型配置与权重的目录。' }}</p>
      <ServerVideoPicker
        v-model="registerPath"
        kind="model"
        :allow-directory-selection="registerKind === 'grounding_dino'"
        :allow-create="false"
      />
    </div>
    <template #footer>
      <el-button @click="registerOpen = false">取消</el-button>
      <el-button type="primary" :loading="registering" :disabled="!registerName.trim() || !registerPath" @click="submitModelRegistration">创建入库任务</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.annotation-focus-tools,
.focus-title,
.focus-actions,
.auto-bar,
.auto-controls,
.frame-controls,
.image-info header,
.object-list > header,
.minimap header,
.frame-grid-overlay > header {
  display: flex;
  align-items: center;
}

.annotation-focus-tools { justify-content: space-between; gap: 16px; height: 100%; margin-left: 20px; }
.focus-title { min-width: 0; gap: 12px; }
.focus-title strong { max-width: 48vw; overflow: hidden; color: #edf3f6; font-size: 15px; text-overflow: ellipsis; white-space: nowrap; }
.focus-title span,
.save-state { color: #92a2ae; font: 12px var(--vdw-mono); white-space: nowrap; }
.save-state[data-state='dirty'] { color: #f3c76d; }
.focus-actions { gap: 12px; }
.focus-actions button { height: 31px; padding: 0 13px; color: #e9f0f4; background: #24323d; border: 1px solid #40515e; cursor: pointer; }

.annotation-workbench {
  position: relative;
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr) 292px;
  grid-template-rows: 50px minmax(0, 1fr) 118px;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  color: #dce5eb;
  background: #111820;
}

.auto-bar { grid-column: 1 / -1; gap: 14px; justify-content: space-between; min-width: 0; padding: 0 10px; overflow: hidden; background: #1d2933; border-bottom: 1px solid #33414c; }
.auto-controls,
.frame-controls { gap: 7px; min-width: 0; white-space: nowrap; }
.auto-controls label,
.frame-controls label { display: flex; align-items: center; gap: 5px; color: #aebbc4; font-size: 12px; }
.model-select { width: 138px; }
.category-select { width: 190px; }
.auto-controls :deep(.el-input-number) { width: 92px; }
.auto-bar button { height: 30px; padding: 0 10px; color: #dce5eb; background: #263641; border: 1px solid #41515d; }
.auto-bar button:disabled { color: #6f7d87; cursor: not-allowed; }
.auto-warning { width: 84px; overflow: hidden; color: #d7a85b; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }

.tool-rail { display: flex; grid-row: 2 / 4; flex-direction: column; align-items: center; gap: 5px; padding: 8px 0; overflow-y: auto; background: #1a252e; border-right: 1px solid #33414c; }
.tool-rail button { display: grid; place-items: center; flex: 0 0 34px; width: 38px; padding: 0; color: #b9c6cf; font: 700 13px var(--vdw-mono); background: transparent; border: 1px solid transparent; border-radius: 3px; cursor: pointer; transition: background 150ms ease, border-color 150ms ease, color 150ms ease; }
.tool-rail button:hover:not(:disabled),
.tool-rail button.active { color: #9de0cc; background: #233740; border-color: #3d665d; }
.tool-rail button:disabled { color: #52616c; cursor: not-allowed; }
.tool-rail output { width: 48px; color: #91a0ab; font: 11px var(--vdw-mono); text-align: center; }
.tool-separator { flex: 0 0 1px; width: 34px; margin: 2px 0; background: #34424d; }

.canvas-panel { position: relative; grid-column: 2; grid-row: 2; min-width: 0; min-height: 0; overflow: hidden; }
.category-picker { position: absolute; z-index: 8; display: grid; grid-template-columns: minmax(130px, 1fr) auto auto; gap: 6px; max-width: calc(100% - 12px); padding: 8px; background: #f7fafb; border: 1px solid #9fb0bb; box-shadow: 0 8px 24px rgb(0 0 0 / 28%); transform: translate(-50%, 10px); }
.category-picker label { display: grid; gap: 3px; color: #51606b; font-size: 11px; }
.category-picker select { min-width: 140px; height: 29px; }
.category-picker button { align-self: end; height: 29px; }
.panel-overlay { position: absolute; inset: 0; z-index: 7; display: grid; place-items: center; color: #afbdc6; background: rgb(12 18 23 / 62%); }
.panel-overlay--passive { pointer-events: none; background: rgb(12 18 23 / 22%); }

.info-panel { display: grid; grid-column: 3; grid-row: 2; grid-template-rows: auto minmax(0, 1fr) 168px; min-height: 0; background: #f6f8f9; border-left: 1px solid #33414c; color: #24313a; }
.image-info,
.object-list,
.minimap { min-width: 0; }
.image-info { padding: 11px 12px; border-bottom: 1px solid #d2dae0; }
.image-info header,
.object-list > header,
.minimap header { justify-content: space-between; height: 27px; }
.image-info header strong,
.object-list header strong,
.minimap header strong { font-size: 13px; }
.image-info header span,
.object-list header span,
.minimap header span { color: #74818b; font: 11px var(--vdw-mono); }
.image-info dl { display: grid; grid-template-columns: 54px minmax(0, 1fr); gap: 5px 8px; margin: 5px 0 0; font-size: 12px; }
.image-info dt { color: #7a8790; }
.image-info dd { min-width: 0; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.object-list { overflow-y: auto; padding: 8px 10px; }
.empty-copy { margin: 20px 0; color: #84919a; font-size: 12px; text-align: center; }
.object-group { margin-top: 5px; border: 1px solid #d4dce1; background: white; }
.object-group-row { display: grid; grid-template-columns: 9px minmax(0, 1fr) 28px 27px 27px; align-items: center; min-height: 34px; padding: 0 5px 0 8px; }
.object-group-row i { width: 8px; height: 8px; border-radius: 50%; }
.object-group-row button { height: 26px; padding: 0; color: #4c5b65; background: transparent; border: 0; cursor: pointer; }
.object-group-row .group-name { overflow: hidden; padding-left: 7px; font-weight: 650; text-align: left; text-overflow: ellipsis; white-space: nowrap; }
.object-group-row span { color: #70808b; font: 11px var(--vdw-mono); text-align: center; }
.box-list { border-top: 1px solid #e0e5e9; }
.box-list button { display: grid; grid-template-columns: 27px minmax(0, 1fr); width: 100%; min-height: 29px; align-items: center; padding: 0 7px; color: #5d6c76; text-align: left; background: #fafcfc; border: 0; border-bottom: 1px solid #edf0f2; cursor: pointer; }
.box-list button.selected { color: #116d5b; background: #e2f2ed; }
.box-list code { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.minimap { padding: 8px 10px 10px; border-top: 1px solid #d2dae0; }
.minimap-image { position: relative; height: 122px; overflow: hidden; background: #17212b; }
.minimap-image img { width: 100%; height: 100%; object-fit: contain; }
.viewport-box { position: absolute; border: 2px solid #78d2b8; background: rgb(120 210 184 / 8%); box-shadow: 0 0 0 1px rgb(23 33 43 / 45%); pointer-events: none; }

.filmstrip { display: grid; grid-column: 2 / 4; grid-row: 3; grid-template-columns: minmax(0, 1fr) 38px; min-width: 0; min-height: 0; background: #18232c; border-top: 1px solid #33414c; }
.filmstrip-scroll { display: flex; align-items: end; gap: 7px; min-width: 0; padding: 8px 8px 9px; overflow-x: auto; overflow-y: hidden; }
.film-frame { position: relative; flex: 0 0 128px; height: 92px; overflow: hidden; padding: 0; background: #0e151b; border: 2px solid transparent; cursor: pointer; }
.film-frame.current { border-color: #78d2b8; box-shadow: 0 0 0 1px #16866f; }
.film-frame.disabled { opacity: .45; }
.film-frame img { width: 100%; height: 100%; object-fit: cover; }
.film-frame span { position: absolute; right: 3px; bottom: 3px; padding: 2px 4px; color: #eef4f6; font: 10px var(--vdw-mono); background: rgb(10 16 20 / 76%); }
.expand-grid { color: #b8c5ce; background: #22303a; border: 0; border-left: 1px solid #34434e; cursor: pointer; }

.frame-grid-overlay { position: absolute; inset: 50px 0 0 58px; z-index: 20; display: grid; grid-template-rows: 48px minmax(0, 1fr); background: #152029; }
.frame-grid-overlay > header { gap: 12px; padding: 0 14px; background: #1e2c36; border-bottom: 1px solid #3a4a56; }
.frame-grid-overlay > header span { color: #91a0ab; font-size: 12px; }
.frame-grid-overlay > header button { margin-left: auto; height: 30px; color: #dbe5eb; background: #283843; border: 1px solid #41515d; }
.frame-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(172px, 1fr)); gap: 9px; align-content: start; padding: 12px; overflow: auto; }
.frame-grid button { overflow: hidden; padding: 0; color: #d7e0e6; text-align: left; background: #1f2b35; border: 2px solid transparent; }
.frame-grid button.current { border-color: #78d2b8; }
.frame-grid button.disabled { opacity: .45; }
.frame-grid img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; }
.frame-grid span { display: block; padding: 6px; font: 11px var(--vdw-mono); }

.workbench-state { position: absolute; inset: 50px 0 0 58px; z-index: 30; display: grid; place-content: center; gap: 12px; color: #aebbc4; background: #111820; text-align: center; }
.workbench-state.error { color: #f0a39e; }
.workbench-state button { justify-self: center; height: 32px; color: #dce6eb; background: #253640; border: 1px solid #455762; }
.shortcut-list { display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 9px 15px; margin: 0; }
.shortcut-list dt { font: 12px var(--vdw-mono); }
.shortcut-list dd { margin: 0; color: #687482; }
.stats-summary { display: grid; grid-template-columns: repeat(3, auto); align-items: baseline; gap: 8px 15px; }
.stats-summary strong { color: var(--vdw-teal); font: 700 24px var(--vdw-mono); }
.stats-summary span { color: #687482; }
.model-registration-form { display: grid; gap: 14px; }
.model-registration-form > label { display: grid; grid-template-columns: 92px minmax(0, 1fr); align-items: center; gap: 12px; }
.model-registration-form > label > span { color: #5f6c76; font-size: 13px; }
.model-registration-form > p { margin: 0; color: #687482; font-size: 13px; }

@media (max-width: 1180px) {
  .annotation-workbench { grid-template-columns: 54px minmax(0, 1fr) 250px; }
  .auto-controls label { display: none; }
  .category-select { width: 160px; }
}

@media (prefers-reduced-motion: reduce) {
  .annotation-workbench *,
  .annotation-focus-tools * { scroll-behavior: auto !important; transition: none !important; }
}
</style>
