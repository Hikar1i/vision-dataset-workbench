<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowDownBold,
  ArrowUpBold,
  Back,
  Delete as DeleteIcon,
  DeleteFilled,
  FullScreen,
  Hide,
  QuestionFilled,
  Rank,
  Refresh,
  Right,
  View,
  ZoomIn,
  ZoomOut,
} from '@element-plus/icons-vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
  getXAnyLabelingSetting,
  listModelProjectModels,
  listModelProjects,
  listXAnyLabelingModels,
  runFrameAutoAnnotation,
  saveXAnyLabelingSetting,
  type AutoAnnotationConfig,
  type InferenceModel,
  type ModelProject,
  type RemoteModelOption,
  type XAnyLabelingSetting,
} from '../api/models'
import { listLLMConfigs, type LLMConfig } from '../api/llm'
import { getProject } from '../api/projects'
import AnnotationCanvas from '../components/AnnotationCanvas.vue'
import FrameAnnotationThumbnail from '../components/FrameAnnotationThumbnail.vue'
import { formatFrameFileName } from '../components/framePresentation'
import { type BoxBounds } from './annotationGeometry'
import { createAnnotationHistory } from './annotationHistory'
import { createAnnotationId } from './annotationId'
import {
  loadAnnotationPreference,
  saveAnnotationPreference,
} from './annotationPreferences'

type CanvasMode = 'select' | 'draw' | 'pan'
type CanvasApi = { zoomBy: (factor: number) => void; resetView: () => void; zoomPercent: number }
type SaveContext = 'switch' | 'close' | 'batch'
type ModelSourceValue = 'xanylabeling' | 'online' | `project:${string}`

const route = useRoute()
const router = useRouter()
const projectId = String(route.params.id)
const videoId = String(route.params.videoId)
const storedPreference = loadAnnotationPreference(projectId)
const canvasRef = ref<CanvasApi | null>(null)
const workbenchRoot = ref<HTMLElement | null>(null)
const video = ref<Video | null>(null)
const frames = ref<Frame[]>([])
const labels = ref<ProjectLabel[]>([])
const inferenceModels = ref<InferenceModel[]>([])
const modelProjects = ref<ModelProject[]>([])
const remoteModels = ref<RemoteModelOption[]>([])
const llmConfigs = ref<LLMConfig[]>([])
const xanylabelingSetting = ref<XAnyLabelingSetting | null>(null)
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
const saveContext = ref<SaveContext | null>(null)
const error = ref('')
const saveText = ref('已同步')
const hiddenLabelIds = ref<string[]>([])
const hiddenAnnotationIds = ref<string[]>([])
const expandedLabelIds = ref<string[]>([])
const crosshair = ref(true)
const overwrite = ref(false)
const gridOpen = ref(false)
const filmstripVisible = ref(true)
const shortcutsOpen = ref(false)
const statsOpen = ref(false)
const imageInfoExpanded = ref(true)
const selectedSource = ref<ModelSourceValue>('' as ModelSourceValue)
const modelListLoading = ref(false)
const xanylabelingSettingsOpen = ref(false)
const xanylabelingSettingsSaving = ref(false)
const xanylabelingServerUrl = ref('')
const xanylabelingApiKey = ref('')
const clearXAnyLabelingApiKey = ref(false)
const inferenceRunning = ref(false)
const activeAutoTask = ref<ProjectTask | null>(null)
const pendingBounds = ref<BoxBounds | null>(null)
const lastLabelId = ref(storedPreference.labelId)
const lastUsedLabelId = ref(storedPreference.labelId)
const reuseLabel = ref(storedPreference.reuse)
const viewport = ref<BoxBounds | null>(null)
const autoModel = ref('')
const autoCategories = ref<string[]>(['__all__'])
const categoryQuery = ref('')
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
  if (!currentFrame.value || !video.value) return ''
  return formatFrameFileName(
    video.value.short_code,
    currentFrame.value.sequence,
    sampling.value?.output_format ?? 'jpg',
  )
})
const enabledLabels = computed(() => labels.value.filter((label) => label.enabled))
const readyModels = computed(() => inferenceModels.value.filter((model) => {
  if (model.status !== 'ready') return false
  return capabilities.value?.features.yolo_auto_annotation.available === true
}))
const selectedLocalModel = computed(() =>
  inferenceModels.value.find((model) => model.id === autoModel.value) ?? null,
)
const selectedRemoteModel = computed(() =>
  remoteModels.value.find((model) => model.key === autoModel.value) ?? null,
)
const selectedOnlineModel = computed(() =>
  llmConfigs.value.find((model) => model.id === autoModel.value) ?? null,
)
const selectedModelName = computed(() => selectedSource.value === 'xanylabeling'
  ? selectedRemoteModel.value?.name ?? ''
  : selectedSource.value === 'online'
    ? selectedOnlineModel.value?.name ?? ''
  : selectedLocalModel.value?.name ?? '')
const batchActive = computed(() =>
  activeAutoTask.value?.type === 'auto_annotate'
  && ['queued', 'running'].includes(activeAutoTask.value.status),
)
const autoUnavailableReason = computed(() => {
  if (selectedSource.value === 'xanylabeling') {
    if (xanylabelingSetting.value?.available && remoteModels.value.length) return ''
    return xanylabelingSetting.value?.configured
      ? 'X-anylabeling-server 当前不可用'
      : '尚未配置 X-anylabeling-server'
  }
  if (selectedSource.value === 'online') {
    return selectedOnlineModel.value?.enabled && selectedOnlineModel.value.available
      ? ''
      : '尚无可用的在线大模型配置'
  }
  if (readyModels.value.length) return ''
  return capabilities.value?.features.yolo_auto_annotation.reason
    ?? '没有可用的已入库模型'
})
const autoUnavailableText = computed(() => {
  if (selectedSource.value === 'xanylabeling') return '远程模型不可用'
  const yolo = capabilities.value?.features.yolo_auto_annotation.available
  return yolo === false ? 'GPU功能不可用' : '暂无可用模型'
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
const enabledFrameCount = computed(() => frames.value.filter((frame) => frame.enabled).length)
const boxCount = computed(() => annotations.value.length)
const allAnnotationStats = computed(() => {
  const counts = new Map<string, number>()
  let total = 0
  for (const frame of frames.value) {
    const items = frame.id === currentFrame.value?.id
      ? annotations.value
      : (frame.annotations ?? [])
    total += items.length
    for (const item of items) counts.set(item.label_id, (counts.get(item.label_id) ?? 0) + 1)
  }
  return {
    total,
    categories: [...labels.value]
      .sort((left, right) => left.sort_order - right.sort_order)
      .map((label) => ({ label, count: counts.get(label.id) ?? 0 }))
      .filter((item) => item.count > 0),
  }
})
const annotationOrder = computed(() => new Map(
  annotations.value.map((item, index) => [item.id, index + 1]),
))
const labelColors = computed(() => Object.fromEntries(
  labels.value.map((label) => [label.id, label.color]),
))
const normalizedCategoryQuery = computed(() => categoryQuery.value.trim().toLowerCase())
const visibleAutoLabels = computed(() => enabledLabels.value.filter(
  (label) => !normalizedCategoryQuery.value || label.name.includes(normalizedCategoryQuery.value),
))
const newAutoCategory = computed(() => {
  const name = normalizedCategoryQuery.value
  if (!name || enabledLabels.value.some((label) => label.name === name)) return ''
  return name
})

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
  deleteAnnotation(selectedId.value)
}

function deleteAnnotation(id: string) {
  pushDraft(annotations.value.filter((item) => item.id !== id))
  hiddenAnnotationIds.value = hiddenAnnotationIds.value.filter((item) => item !== id)
  if (selectedId.value === id) selectedId.value = null
}

function clearAll() {
  if (!annotations.value.length) return
  pushDraft([])
  selectedId.value = null
}

function requestCategory(bounds: BoxBounds) {
  const reusable = enabledLabels.value.some((label) => label.id === lastUsedLabelId.value)
  if (reuseLabel.value && reusable) {
    addManualBox(bounds, lastUsedLabelId.value)
    return
  }
  pendingBounds.value = bounds
  if (!lastLabelId.value) lastLabelId.value = enabledLabels.value[0]?.id ?? ''
}

function addManualBox(bounds: BoxBounds, labelId: string) {
  const item: FrameAnnotation = {
    id: createAnnotationId(),
    label_id: labelId,
    ...bounds,
    source: 'manual',
    confidence: null,
  }
  pushDraft([...annotations.value, item])
  selectedId.value = item.id
  lastLabelId.value = labelId
  lastUsedLabelId.value = labelId
  saveAnnotationPreference(projectId, { reuse: reuseLabel.value, labelId })
  pendingBounds.value = null
  mode.value = 'select'
}

function confirmCategory() {
  if (!pendingBounds.value || !lastLabelId.value) return
  addManualBox(pendingBounds.value, lastLabelId.value)
}

function cancelCategory() {
  pendingBounds.value = null
  mode.value = 'select'
}

async function saveCurrent(context?: SaveContext) {
  const frame = currentFrame.value
  if (!frame || !dirty.value) return true
  saving.value = true
  saveContext.value = context ?? null
  saveText.value = '保存中…'
  try {
    const saved = await replaceFrameAnnotations(projectId, videoId, {
      frame_id: frame.id,
      annotation_revision: annotationRevision.value,
      items: clone(annotations.value),
    })
    annotations.value = clone(saved.items)
    frame.annotations = clone(saved.items)
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
    saveContext.value = null
  }
}

function setAutoCategories(values: string[]) {
  const selectedAll = values.includes('__all__')
  const hadAll = autoCategories.value.includes('__all__')
  autoCategories.value = selectedAll && !hadAll
    ? ['__all__']
    : values.filter((value) => value !== '__all__')
  categoryQuery.value = ''
}

function selectedModelProjectId() {
  return selectedSource.value.startsWith('project:')
    ? selectedSource.value.slice('project:'.length)
    : ''
}

async function openXAnyLabelingSettings() {
  if (!xanylabelingSetting.value) {
    xanylabelingSetting.value = await getXAnyLabelingSetting()
  }
  xanylabelingServerUrl.value = xanylabelingSetting.value.server_url
  xanylabelingApiKey.value = ''
  clearXAnyLabelingApiKey.value = false
  xanylabelingSettingsOpen.value = true
}

async function changeModelSource(value: ModelSourceValue) {
  selectedSource.value = value
  autoModel.value = ''
  if (value === 'xanylabeling') {
    await openXAnyLabelingSettings()
    return
  }
  await refreshSelectedModels()
}

async function refreshSelectedModels() {
  modelListLoading.value = true
  try {
    if (selectedSource.value === 'xanylabeling') {
      remoteModels.value = await listXAnyLabelingModels()
      if (xanylabelingSetting.value) {
        xanylabelingSetting.value = { ...xanylabelingSetting.value, available: true }
      }
      autoModel.value = remoteModels.value[0]?.key ?? ''
      return
    }
    if (selectedSource.value === 'online') {
      llmConfigs.value = (await listLLMConfigs()).filter((item) => item.enabled)
      autoModel.value = llmConfigs.value.find((item) => item.available)?.id ?? ''
      return
    }
    const modelProjectId = selectedModelProjectId()
    inferenceModels.value = modelProjectId
      ? await listModelProjectModels(modelProjectId)
      : []
    autoModel.value = readyModels.value[0]?.id ?? ''
  } catch (reason) {
    if (selectedSource.value === 'xanylabeling') {
      remoteModels.value = []
      if (xanylabelingSetting.value) {
        xanylabelingSetting.value = { ...xanylabelingSetting.value, available: false }
      }
    } else {
      inferenceModels.value = []
    }
    autoModel.value = ''
    ElMessage.error(reason instanceof Error ? reason.message : '模型列表刷新失败')
  } finally {
    modelListLoading.value = false
  }
}

async function saveXAnyLabelingSettings() {
  if (!xanylabelingServerUrl.value.trim()) return
  xanylabelingSettingsSaving.value = true
  try {
    const mode = clearXAnyLabelingApiKey.value
      ? 'clear'
      : xanylabelingApiKey.value ? 'replace' : 'retain'
    const saved = await saveXAnyLabelingSetting(
      xanylabelingServerUrl.value,
      mode,
      mode === 'replace' ? xanylabelingApiKey.value : null,
    )
    xanylabelingSetting.value = saved.setting
    remoteModels.value = saved.models
    selectedSource.value = 'xanylabeling'
    autoModel.value = saved.models[0]?.key ?? ''
    xanylabelingSettingsOpen.value = false
    ElMessage.success('X-anylabeling-server 设置已保存。')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '远程服务器设置保存失败')
  } finally {
    xanylabelingSettingsSaving.value = false
  }
}

function autoConfig(): AutoAnnotationConfig | null {
  const local = selectedLocalModel.value
  const remote = selectedRemoteModel.value
  if (selectedSource.value === 'xanylabeling' ? !remote : selectedSource.value === 'online' ? !selectedOnlineModel.value : !local) {
    ElMessage.warning('请先选择可用模型。')
    return null
  }
  const categories = autoCategories.value.includes('__all__')
    ? []
    : [...new Set(autoCategories.value.map((item) => item.trim().toLowerCase()).filter(Boolean))]
  return {
    source: selectedSource.value === 'xanylabeling'
      ? 'xanylabeling'
      : selectedSource.value === 'online' ? 'online' : 'local',
    model_id: remote?.model_id ?? local?.id ?? '',
    remote_task_id: remote?.task_id ?? null,
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
  if (!config || batchActive.value) return
  const categoryText = config.categories.length ? config.categories.join(', ') : 'All / 全类别'
  try {
    await ElMessageBox.confirm(
      `将使用「${selectedModelName.value}」处理 ${enabledFrameCount.value} 个启用采样帧；类别：${categoryText}；${overwrite.value ? '覆盖已有标注' : '保留已有标注并追加结果'}。`,
      '确认批量自动标注',
      {
        confirmButtonText: '确认运行',
        cancelButtonText: '取消',
        type: overwrite.value ? 'error' : 'warning',
        customClass: 'batch-confirm-dialog',
        modalClass: 'batch-confirm-mask',
      },
    )
  } catch {
    return
  }
  if (!await saveCurrent('batch')) return
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
      const modelProjectId = selectedModelProjectId()
      inferenceModels.value = modelProjectId
        ? await listModelProjectModels(modelProjectId)
        : []
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
    hiddenAnnotationIds.value = []
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
  if (!await saveCurrent('switch')) return
  await loadFrame(index)
}

async function closeWorkbench() {
  if (!await saveCurrent('close')) return
  await router.push(`/projects/${projectId}/videos`)
}

async function toggleFrameEnabled(value: boolean | string | number) {
  const frame = currentFrame.value
  if (!frame || !sampling.value) return
  try {
    sampling.value = await setFramesEnabled(
      projectId,
      videoId,
      [{ frame_id: frame.id, enabled: Boolean(value) }],
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

function toggleAnnotationHidden(annotationId: string) {
  const hiding = !hiddenAnnotationIds.value.includes(annotationId)
  hiddenAnnotationIds.value = hiding
    ? [...hiddenAnnotationIds.value, annotationId]
    : hiddenAnnotationIds.value.filter((id) => id !== annotationId)
  if (hiding && selectedId.value === annotationId) selectedId.value = null
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

function expandAllObjects() {
  expandedLabelIds.value = groupedObjects.value.map(({ label }) => label.id)
}

function collapseAllObjects() {
  expandedLabelIds.value = []
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
  if (pendingBounds.value && event.key === 'Escape') {
    event.preventDefault()
    cancelCategory()
    return
  }
  if (isInputTarget(event.target) || event.repeat || pendingBounds.value) return
  const key = event.key.toLowerCase()
  if (batchActive.value && ['r', 'delete', 'z', 's', 'y', 'l', 'p'].includes(key)) return
  if ((event.ctrlKey || event.metaKey) && key === 'z') {
    event.preventDefault()
    event.shiftKey ? redo() : undo()
    return
  }
  if (key === 'a') void switchFrame(currentIndex.value - 1)
  else if (key === 'd') void switchFrame(currentIndex.value + 1)
  else if (key === 'r') mode.value = 'draw'
  else if (key === 's' && currentFrame.value) void toggleFrameEnabled(!currentFrame.value.enabled)
  else if (key === 'y') reuseLabel.value = !reuseLabel.value
  else if (key === 'l') crosshair.value = !crosshair.value
  else if (key === 'h') toggleAllBoxes()
  else if (key === 'p' && !inferenceRunning.value && autoModel.value) void runSingleAutoAnnotation()
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
  const first = await listFrames(projectId, videoId, 1, 200, undefined, true)
  sampling.value = first.sampling
  const pages = Math.ceil(first.total / first.page_size)
  const rest = pages > 1
    ? await Promise.all(
        Array.from({ length: pages - 1 }, (_, index) =>
          listFrames(projectId, videoId, index + 2, first.page_size, undefined, true)),
      )
    : []
  frames.value = [first, ...rest].flatMap((page) => page.items)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [project, videos, projectLabels, projects, remoteSetting, detectedCapabilities, user] = await Promise.all([
      getProject(projectId),
      listVideos(projectId, 1, 999),
      listLabels(projectId),
      listModelProjects(),
      getXAnyLabelingSetting(),
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
    modelProjects.value = projects
    xanylabelingSetting.value = remoteSetting
    capabilities.value = detectedCapabilities
    currentUser.value = user
    activeAutoTask.value = video.value.latest_task?.type === 'auto_annotate'
      ? video.value.latest_task
      : null
    const firstProject = projects[0]
    if (firstProject) {
      selectedSource.value = `project:${firstProject.id}`
      inferenceModels.value = await listModelProjectModels(firstProject.id)
      autoModel.value = inferenceModels.value.find((model) => (
        model.status === 'ready'
        && detectedCapabilities.features.yolo_auto_annotation.available
      ))?.id ?? ''
    } else if (remoteSetting.configured) {
      selectedSource.value = 'xanylabeling'
      await refreshSelectedModels()
    }
    const remembered = projectLabels.find(
      (label) => label.enabled && label.id === lastUsedLabelId.value,
    )
    if (!remembered) lastUsedLabelId.value = ''
    lastLabelId.value = remembered?.id
      ?? projectLabels.find((label) => label.enabled)?.id
      ?? ''
    saveAnnotationPreference(projectId, {
      reuse: reuseLabel.value,
      labelId: lastUsedLabelId.value,
    })
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

watch(reuseLabel, (reuse) => {
  saveAnnotationPreference(projectId, { reuse, labelId: lastUsedLabelId.value })
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
        <button data-test="stats-action" class="primary-action" type="button" @click="statsOpen = true">标注统计</button>
        <button type="button" data-test="close-annotation" title="保存并关闭" :disabled="saving" @click="closeWorkbench">关闭</button>
      </div>
    </div>
  </Teleport>

  <main ref="workbenchRoot" class="annotation-workbench" :class="{ 'filmstrip-hidden': !filmstripVisible }" data-test="annotation-workbench">
    <section class="auto-bar" aria-label="自动标注控制">
      <div class="auto-controls">
        <el-select
          :model-value="selectedSource"
          data-test="model-project-select"
          class="model-project-select"
          :class="selectedSource === 'xanylabeling'
            ? (xanylabelingSetting?.available ? 'remote-source-available' : 'remote-source-unavailable')
            : ''"
          placeholder="选择模型项目"
          :title="selectedSource === 'xanylabeling'
            ? `X-anylabeling-server ${xanylabelingSetting?.available ? '可用' : '不可用'}`
            : '选择模型项目'"
          :disabled="batchActive || inferenceRunning"
          @change="changeModelSource"
        >
          <el-option
            value="xanylabeling"
            label="X-anylabeling-server"
            :class="xanylabelingSetting?.available ? 'remote-source-available' : 'remote-source-unavailable'"
          >
            <span @click="openXAnyLabelingSettings">
              X-anylabeling-server（{{ xanylabelingSetting?.available ? '可用' : '不可用' }}）
            </span>
          </el-option>
          <el-option value="online" label="在线大模型" />
          <el-option
            v-for="modelProject in modelProjects"
            :key="modelProject.id"
            :label="modelProject.name"
            :value="`project:${modelProject.id}`"
          />
        </el-select>
        <button
          data-test="model-list-refresh"
          type="button"
          title="刷新模型列表"
          aria-label="刷新模型列表"
          :disabled="modelListLoading || batchActive || inferenceRunning || !selectedSource"
          @click="refreshSelectedModels"
        >
          <el-icon><Refresh /></el-icon>
        </button>
        <el-select
          v-model="autoModel"
          data-test="inference-model-select"
          class="model-select"
          placeholder="选择模型"
          :disabled="batchActive || inferenceRunning || modelListLoading"
        >
          <template v-if="selectedSource === 'xanylabeling'">
            <el-option v-for="model in remoteModels" :key="model.key" :label="model.name" :value="model.key" />
          </template>
          <template v-else>
            <template v-if="selectedSource === 'online'">
              <el-option v-for="model in llmConfigs" :key="model.id" :label="model.name" :value="model.id" />
            </template>
            <template v-else>
              <el-option v-for="model in readyModels" :key="model.id" :label="model.name" :value="model.id" />
            </template>
          </template>
        </el-select>
        <el-select
          :model-value="autoCategories"
          class="category-select"
          data-test="auto-categories"
          multiple
          filterable
          collapse-tags
          placeholder="类别"
          :disabled="batchActive || inferenceRunning || !autoModel"
          :filter-method="(query: string) => { categoryQuery = query }"
          @change="setAutoCategories"
        >
          <el-option v-if="newAutoCategory" :label="`新建类别：${newAutoCategory}`" :value="newAutoCategory" />
          <el-option v-if="!normalizedCategoryQuery || 'all'.includes(normalizedCategoryQuery)" label="All / 全类别" value="__all__" />
          <el-option v-for="label in visibleAutoLabels" :key="label.id" :label="label.name" :value="label.name" />
        </el-select>
        <label>置信度 <el-input-number v-model="confidence" controls-position="right" :min="0" :max="1" :step="0.05" :precision="2" :disabled="batchActive || inferenceRunning" /></label>
        <label>IoU <el-input-number v-model="iou" controls-position="right" :min="0" :max="1" :step="0.05" :precision="2" :disabled="batchActive || inferenceRunning" /></label>
        <label>标签覆盖 <el-switch v-model="overwrite" data-test="overwrite-switch" :disabled="batchActive || inferenceRunning || !autoModel" /></label>
        <button data-test="run-single-auto" class="primary-action" type="button" :disabled="batchActive || inferenceRunning || !autoModel" @click="runSingleAutoAnnotation">单张运行</button>
        <button data-test="run-batch-auto" class="primary-action" type="button" :disabled="batchActive || inferenceRunning || !autoModel || video?.enabled === false" @click="runBatchAutoAnnotation">批量运行</button>
        <span v-if="autoUnavailableReason" class="auto-warning" :title="autoUnavailableReason">{{ autoUnavailableText }}</span>
      </div>
      <div class="frame-controls">
        <label>启用帧 <el-switch :model-value="currentFrame?.enabled ?? false" data-test="frame-enabled-switch" :disabled="!currentFrame || batchActive" @change="toggleFrameEnabled" /></label>
        <label>标签沿用 <el-switch v-model="reuseLabel" data-test="reuse-label-switch" :disabled="batchActive" /></label>
        <label>十字线 <el-switch v-model="crosshair" data-test="crosshair-switch" :disabled="batchActive" /></label>
      </div>
    </section>

    <aside class="tool-rail" aria-label="标注工具">
      <button data-test="pan-tool" :class="{ active: mode === 'pan' }" type="button" title="拖拽（按住 Space）" @click="mode = mode === 'pan' ? 'select' : 'pan'">
        <el-icon><Rank /></el-icon>
      </button>
      <button data-test="previous-frame" type="button" title="上一张（A）" :disabled="currentIndex === 0" @click="switchFrame(currentIndex - 1)">
        <el-icon><Back /></el-icon>
      </button>
      <button data-test="next-frame" type="button" title="下一张（D）" :disabled="currentIndex >= frames.length - 1" @click="switchFrame(currentIndex + 1)">
        <el-icon><Right /></el-icon>
      </button>
      <button :class="{ active: mode === 'draw' }" type="button" title="新建矩形框（R）" :disabled="batchActive" @click="mode = 'draw'">
        <svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 18 18" width="1em" height="1em" aria-hidden="true" focusable="false" class=""><g clip-path="url(#rectangle_svg__a)"><path d="M17.196 4.598a.304.304 0 0 0 .304-.303V.804A.304.304 0 0 0 17.196.5h-3.49a.304.304 0 0 0-.304.304v1.062H4.598V.804A.304.304 0 0 0 4.295.5H.804A.304.304 0 0 0 .5.804v3.49c0 .168.137.304.304.304h1.062v8.804H.804a.304.304 0 0 0-.304.303v3.492c0 .166.137.303.304.303h3.49a.304.304 0 0 0 .304-.303v-1.063h8.804v1.063c0 .166.136.303.303.303h3.491a.304.304 0 0 0 .304-.303v-3.492a.304.304 0 0 0-.304-.303h-1.062V4.598zm-2.58-2.884h1.67v1.67h-1.67zM1.714 3.384v-1.67h1.67v1.67zm1.67 12.902h-1.67v-1.67h1.67zm12.902-1.67v1.67h-1.67v-1.67zm-1.518-1.214h-1.063a.304.304 0 0 0-.303.303v1.063H4.598v-1.063a.304.304 0 0 0-.303-.303H3.232V4.598h1.063a.304.304 0 0 0 .303-.303V3.232h8.804v1.063c0 .167.136.303.303.303h1.063z"></path></g><defs><clipPath id="rectangle_svg__a"><path fill="#fff" d="M0 0h18v18H0z"></path></clipPath></defs></svg>
      </button>
      <button data-test="toggle-all-boxes" type="button" :title="allBoxesHidden ? '显示全部标注框' : '隐藏全部标注框'" @click="toggleAllBoxes">
        <el-icon><View v-if="allBoxesHidden" /><Hide v-else /></el-icon>
      </button>
      <button type="button" title="清空所有标注框" :disabled="batchActive || !annotations.length" @click="clearAll">
        <el-icon><DeleteFilled /></el-icon>
      </button>
      <button type="button" title="撤销（Ctrl+Z）" :disabled="batchActive || !history.canUndo()" @click="undo">
        <svg xmlns="http://www.w3.org/2000/svg" class="" viewBox="0 0 1024 1024" width="1em" height="1em" fill="currentColor" aria-hidden="true" focusable="false"><path d="M296.704 145.28 100.608 341.376l196.096 196.117 60.352-60.352L263.893 384h365.44a202.667 202.667 0 0 1 0 405.333H362.667v85.334h266.666c159.062 0 288-128.939 288-288s-128.938-288-288-288H264l93.035-93.056z"></path></svg>
      </button>
      <button type="button" title="重做（Ctrl+Shift+Z）" :disabled="batchActive || !history.canRedo()" @click="redo">
        <svg xmlns="http://www.w3.org/2000/svg" class="" viewBox="0 0 1024 1024" width="1em" height="1em" fill="currentColor" aria-hidden="true" focusable="false"><path d="m727.296 145.28 196.096 196.096-196.096 196.117-60.352-60.352L760.107 384h-365.44a202.667 202.667 0 0 0 0 405.333h266.666v85.334H394.667c-159.062 0-288-128.939-288-288s128.938-288 288-288H760l-93.056-93.056z"></path></svg>
      </button>
      <span class="tool-separator" />
      <button type="button" title="展示全图" @click="canvasRef?.resetView()">
        <el-icon><FullScreen /></el-icon>
      </button>
      <button type="button" title="缩小" @click="canvasRef?.zoomBy(0.9)">
        <el-icon><ZoomOut /></el-icon>
      </button>
      <output>{{ canvasRef?.zoomPercent ?? 100 }}%</output>
      <button type="button" title="放大" @click="canvasRef?.zoomBy(1.1)">
        <el-icon><ZoomIn /></el-icon>
      </button>
      <button type="button" title="快捷键指南" @click="shortcutsOpen = true">
        <el-icon><QuestionFilled /></el-icon>
      </button>
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
        :hidden-annotation-ids="hiddenAnnotationIds"
        :pending-bounds="pendingBounds"
        :readonly="batchActive"
        @change="pushDraft"
        @select="selectedId = $event"
        @request-category="requestCategory"
        @view-change="viewport = $event"
      />
      <div v-if="loadingFrame" class="panel-overlay">正在载入采样帧…</div>
      <div v-else-if="batchActive" class="panel-overlay panel-overlay--passive">批量自动标注运行中 · 当前帧只读</div>
    </section>

    <aside class="info-panel">
      <section class="image-info">
        <header>
          <strong>图像信息</strong>
          <div class="info-heading-actions">
            <span>#{{ currentFrame?.sequence ?? 0 }}</span>
            <button data-test="image-info-toggle" type="button" :title="imageInfoExpanded ? '收起图像信息' : '展开图像信息'" @click="imageInfoExpanded = !imageInfoExpanded">
              <el-icon><ArrowUpBold v-if="imageInfoExpanded" /><ArrowDownBold v-else /></el-icon>
            </button>
          </div>
        </header>
        <dl v-if="imageInfoExpanded">
          <dt>文件名</dt><dd :title="frameFileName">{{ frameFileName }}</dd>
          <dt>尺寸</dt><dd>{{ video?.width ?? 0 }} × {{ video?.height ?? 0 }}</dd>
          <dt>大小</dt><dd>{{ ((currentFrame?.file_size ?? 0) / 1024).toFixed(1) }} KB</dd>
        </dl>
      </section>
      <section class="object-list">
        <header>
          <strong>对象列表</strong>
          <div class="object-heading-actions">
            <span>{{ boxCount }} 个</span>
            <button data-test="expand-all-objects" type="button" title="展开所有类别" aria-label="展开所有类别" :disabled="!groupedObjects.length" @click="expandAllObjects">
              <el-icon><ArrowDownBold /></el-icon>
            </button>
            <button data-test="collapse-all-objects" type="button" title="收起所有类别" aria-label="收起所有类别" :disabled="!expandedLabelIds.length" @click="collapseAllObjects">
              <el-icon><ArrowUpBold /></el-icon>
            </button>
          </div>
        </header>
        <p v-if="!groupedObjects.length" class="empty-copy">当前图像暂无标注框</p>
        <article v-for="group in groupedObjects" :key="group.label.id" class="object-group">
          <div class="object-group-row">
            <i :style="{ background: group.label.color }" />
            <button type="button" class="group-name" @click="toggleExpanded(group.label.id)">{{ group.label.name }}</button>
            <span>{{ group.items.length }}</span>
            <button type="button" :title="hiddenLabelIds.includes(group.label.id) ? '显示类别' : '隐藏类别'" @click="toggleLabelHidden(group.label.id)">
              <el-icon><View v-if="hiddenLabelIds.includes(group.label.id)" /><Hide v-else /></el-icon>
            </button>
            <button type="button" :title="expandedLabelIds.includes(group.label.id) ? '收起类别' : '展开类别'" @click="toggleExpanded(group.label.id)">
              <el-icon><ArrowUpBold v-if="expandedLabelIds.includes(group.label.id)" /><ArrowDownBold v-else /></el-icon>
            </button>
          </div>
          <div v-if="expandedLabelIds.includes(group.label.id)" class="box-list">
            <div
              v-for="item in group.items"
              :key="item.id"
              class="box-item"
              :class="{ selected: selectedId === item.id }"
            >
              <button type="button" class="box-select" @click="selectedId = item.id; mode = 'select'">
                <span>#{{ annotationOrder.get(item.id) }}</span>
                <code>{{ item.x_min }},{{ item.y_min }} → {{ item.x_max }},{{ item.y_max }}</code>
              </button>
              <button type="button" :title="hiddenAnnotationIds.includes(item.id) ? '显示标注框' : '隐藏标注框'" @click="toggleAnnotationHidden(item.id)">
                <el-icon><View v-if="hiddenAnnotationIds.includes(item.id)" /><Hide v-else /></el-icon>
              </button>
              <button type="button" title="删除标注框" :disabled="batchActive" @click="deleteAnnotation(item.id)">
                <el-icon><DeleteIcon /></el-icon>
              </button>
            </div>
          </div>
        </article>
      </section>
      <section class="minimap">
        <header><strong>缩略图</strong><span>{{ canvasRef?.zoomPercent ?? 100 }}%</span></header>
        <div class="minimap-image">
          <svg
            v-if="currentFrame && video"
            class="minimap-svg"
            :viewBox="`0 0 ${video.width} ${video.height}`"
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="当前采样帧缩略图"
          >
            <image :href="imageUrl" :width="video.width" :height="video.height" />
            <rect
              v-if="viewport"
              class="viewport-box"
              :x="viewport.x_min"
              :y="viewport.y_min"
              :width="Math.max(0, viewport.x_max - viewport.x_min)"
              :height="Math.max(0, viewport.y_max - viewport.y_min)"
              vector-effect="non-scaling-stroke"
            />
          </svg>
        </div>
      </section>
    </aside>

    <section v-if="filmstripVisible" class="filmstrip">
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
          <FrameAnnotationThumbnail
            :image-url="frameImageUrl(projectId, videoId, frame.id)"
            :image-width="video?.width ?? 0"
            :image-height="video?.height ?? 0"
            :annotations="index === currentIndex ? annotations : (frame.annotations ?? [])"
            :label-colors="labelColors"
            :sequence="frame.sequence"
            :time-offset="frame.time_offset"
            :current="index === currentIndex"
            :disabled="!frame.enabled"
          />
        </button>
      </div>
      <div class="filmstrip-actions">
        <button type="button" title="展开全部采样帧" @click="gridOpen = true"><el-icon><ArrowUpBold /></el-icon></button>
        <button type="button" title="隐藏采样帧序列" @click="filmstripVisible = false"><el-icon><ArrowDownBold /></el-icon></button>
      </div>
    </section>

    <button v-else class="restore-filmstrip" type="button" title="显示采样帧序列" @click="filmstripVisible = true">
      <el-icon><ArrowUpBold /></el-icon><span>采样帧</span>
    </button>

    <section v-if="gridOpen" class="frame-grid-overlay" aria-label="全部采样帧">
      <header><strong>全部采样帧</strong><span>{{ enabledFrameCount }} / {{ frames.length }} 帧启用</span><button type="button" title="收起全部采样帧" @click="gridOpen = false"><el-icon><ArrowDownBold /></el-icon><span>收起</span></button></header>
      <div data-test="frame-grid" class="frame-grid">
        <button v-for="(frame, index) in frames" :key="frame.id" data-test="frame-grid-card" type="button" class="frame-grid-card" :class="{ current: index === currentIndex, disabled: !frame.enabled }" @click="switchFrame(index).then(() => { gridOpen = false })">
          <FrameAnnotationThumbnail
            :image-url="frameImageUrl(projectId, videoId, frame.id)"
            :image-width="video?.width ?? 0"
            :image-height="video?.height ?? 0"
            :annotations="index === currentIndex ? annotations : (frame.annotations ?? [])"
            :label-colors="labelColors"
            :sequence="frame.sequence"
            :time-offset="frame.time_offset"
            :current="index === currentIndex"
            :disabled="!frame.enabled"
          />
        </button>
      </div>
    </section>

    <div v-if="loading || error" class="workbench-state" :class="{ error: Boolean(error) }">
      <span>{{ error || '正在加载在线标注工作台…' }}</span>
      <button v-if="error" type="button" @click="closeWorkbench">返回原始数据</button>
    </div>
    <div v-if="saving && saveContext" class="save-overlay" data-test="save-overlay">
      <span class="save-spinner" />
      <strong>{{ saveContext === 'close' ? '正在保存并关闭…' : saveContext === 'batch' ? '正在保存后启动任务…' : '正在保存并切换采样帧…' }}</strong>
    </div>
    <div v-if="pendingBounds" class="category-scrim" data-test="category-scrim" />
    <div v-if="pendingBounds" class="category-picker" data-test="category-picker">
      <label>选择类别
        <select v-model="lastLabelId" autofocus>
          <option v-if="!enabledLabels.length" value="">暂无启用类别</option>
          <option v-for="label in enabledLabels" :key="label.id" :value="label.id">{{ label.name }}</option>
        </select>
      </label>
      <button data-test="confirm-category" type="button" :disabled="!lastLabelId" @click="confirmCategory">确认</button>
      <button data-test="cancel-category" type="button" @click="cancelCategory">取消</button>
    </div>
  </main>

  <el-dialog v-model="shortcutsOpen" title="快捷键操作指南" width="460px" append-to-body>
    <dl class="shortcut-list" data-test="shortcut-list">
      <dt>A / D</dt><dd>上一张 / 下一张</dd><dt>R</dt><dd>新建矩形框</dd>
      <dt>Space</dt><dd>按住进入拖拽模式</dd><dt>Ctrl + 滚轮</dt><dd>缩放图像</dd>
      <dt>Ctrl + Z</dt><dd>撤销</dd><dt>Ctrl + Shift + Z</dt><dd>重做</dd>
      <dt>Delete</dt><dd>删除选中标注框</dd>
      <dt>S</dt><dd>启用 / 停用当前帧</dd><dt>Y</dt><dd>开启 / 关闭标签沿用</dd>
      <dt>L</dt><dd>开启 / 关闭十字线</dd><dt>H</dt><dd>显示 / 隐藏全部标注框</dd>
      <dt>P</dt><dd>单张运行模型自动标注</dd>
    </dl>
  </el-dialog>
  <el-dialog v-model="statsOpen" title="当前视频标注统计" width="520px" append-to-body>
    <dl class="stats-summary">
      <div data-test="stats-row"><dt>采样帧</dt><dd>{{ frames.length }}</dd></div>
      <div data-test="stats-row"><dt>启用帧</dt><dd>{{ enabledFrameCount }}</dd></div>
      <div data-test="stats-row"><dt>当前帧标注框</dt><dd>{{ boxCount }}</dd></div>
      <div data-test="stats-row"><dt>所有帧标注框</dt><dd data-test="all-box-count">{{ allAnnotationStats.total }}</dd></div>
      <div v-for="item in allAnnotationStats.categories" :key="item.label.id" :data-test="`stats-category-${item.label.id}`">
        <dt :style="{ color: item.label.color }">{{ item.label.name }}</dt><dd>{{ item.count }}</dd>
      </div>
    </dl>
  </el-dialog>
  <el-dialog
    v-model="xanylabelingSettingsOpen"
    data-test="xanylabeling-settings-dialog"
    title="X-anylabeling-server 设置"
    width="min(560px, calc(100vw - 32px))"
    append-to-body
    :close-on-click-modal="!xanylabelingSettingsSaving"
    :close-on-press-escape="!xanylabelingSettingsSaving"
    :show-close="!xanylabelingSettingsSaving"
  >
    <div class="xanylabeling-settings-form">
      <label>
        <span>服务器地址</span>
        <el-input
          v-model="xanylabelingServerUrl"
          data-test="xanylabeling-server-url"
          placeholder="http://127.0.0.1:44444"
        />
      </label>
      <label>
        <span>API 密钥（可选）</span>
        <el-input
          v-model="xanylabelingApiKey"
          data-test="xanylabeling-api-key"
          type="password"
          show-password
          autocomplete="new-password"
          :placeholder="xanylabelingSetting?.has_api_key ? '已配置，留空则保留' : '未配置'"
        />
      </label>
      <el-checkbox
        v-if="xanylabelingSetting?.has_api_key"
        v-model="clearXAnyLabelingApiKey"
      >清除已保存的 API 密钥</el-checkbox>
    </div>
    <template #footer>
      <el-button :disabled="xanylabelingSettingsSaving" @click="xanylabelingSettingsOpen = false">取消</el-button>
      <el-button
        type="primary"
        :loading="xanylabelingSettingsSaving"
        :disabled="!xanylabelingServerUrl.trim()"
        @click="saveXAnyLabelingSettings"
      >确认</el-button>
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
.save-state { color: #92a2ae; font: 14px var(--vdw-mono); white-space: nowrap; }
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
  color: var(--vdw-focus-ink);
  background: var(--vdw-focus-canvas);
}
.annotation-workbench.filmstrip-hidden { grid-template-rows: 50px minmax(0, 1fr) 0; }

.auto-bar { grid-column: 1 / -1; gap: 14px; justify-content: space-between; min-width: 0; padding: 0 10px; overflow: hidden; background: var(--vdw-focus-panel); border-bottom: 1px solid var(--vdw-focus-rule); }
.auto-controls,
.frame-controls { gap: 10px; min-width: 0; white-space: nowrap; }
.auto-controls label,
.frame-controls label { display: flex; align-items: center; gap: 5px; color: var(--vdw-focus-muted); font-size: 14px; }
.model-project-select { width: 210px; }
.model-select { width: 230px; }
.remote-source-available { color: #16866f; }
.remote-source-unavailable { color: #c45656; }
.remote-source-available :deep(.el-select__selected-item) { color: #16866f; }
.remote-source-unavailable :deep(.el-select__selected-item) { color: #c45656; }
.category-select { width: 340px; }
.auto-controls :deep(.el-input-number) { width: 100px; }
.auto-bar button { height: 30px; padding: 0 10px; color: #dce5eb; background: #263641; border: 1px solid #41515d; }
.auto-bar button:disabled { color: #6f7d87; cursor: not-allowed; }
.auto-bar button.primary-action,
.focus-actions button.primary-action { color: white; background: #16866f; border-color: #16866f; border-radius: 3px; }
.auto-bar button.primary-action:hover:not(:disabled),
.focus-actions button.primary-action:hover:not(:disabled) { background: #137762; border-color: #137762; }
.auto-bar button.primary-action:disabled { color: #7f9d94; background: #28473f; border-color: #365c52; }
.auto-warning { width: 96px; overflow: hidden; color: #e0b869; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }

.tool-rail { display: flex; grid-row: 2 / 4; flex-direction: column; align-items: center; gap: 8px; padding: 8px 0; overflow-y: auto; background: #1a252e; border-right: 1px solid #33414c; }
.tool-rail button { display: grid; place-items: center; flex: 0 0 40px; width: 40px; padding: 0; color: #b9c6cf; font: 700 20px var(--vdw-mono); background: transparent; border: 1px solid transparent; border-radius: 3px; cursor: pointer; transition: background 150ms ease, border-color 150ms ease, color 150ms ease; }
.tool-rail button:hover:not(:disabled),
.tool-rail button.active { color: #9de0cc; background: #233740; border-color: #3d665d; }
.tool-rail button:disabled { color: #52616c; cursor: not-allowed; }
.tool-rail output { width: 48px; color: #91a0ab; font: 11px var(--vdw-mono); text-align: center; }
.tool-separator { flex: 0 0 1px; width: 34px; margin: 2px 0; background: #34424d; }

.canvas-panel { position: relative; grid-column: 2; grid-row: 2; min-width: 0; min-height: 0; overflow: hidden; }
.category-scrim { position: fixed; inset: 0; z-index: 3000; background: rgb(4 8 11 / 52%); }
.category-picker { position: fixed; z-index: 3001; top: 50%; left: 50%; display: grid; grid-template-columns: minmax(170px, 1fr) auto auto; gap: 8px; max-width: calc(100% - 24px); padding: 12px; background: #f7fafb; border: 1px solid #9fb0bb; box-shadow: 0 12px 32px rgb(0 0 0 / 42%); transform: translate(-50%, -50%); }
.category-picker label { display: grid; gap: 3px; color: #51606b; font-size: 11px; }
.category-picker select { min-width: 140px; height: 29px; }
.category-picker button { align-self: end; height: 29px; }
.panel-overlay { position: absolute; inset: 0; z-index: 7; display: grid; place-items: center; color: #afbdc6; background: rgb(12 18 23 / 62%); }
.panel-overlay--passive { pointer-events: none; background: rgb(12 18 23 / 22%); }

.info-panel { display: grid; grid-column: 3; grid-row: 2; grid-template-rows: auto minmax(0, 1fr) 200px; min-height: 0; color: var(--vdw-focus-ink); background: var(--vdw-focus-panel); border-left: 1px solid var(--vdw-focus-rule); }
.image-info,
.object-list,
.minimap { min-width: 0; }
.image-info { padding: 5px 10px 10px 10px; border-bottom: 1px solid var(--vdw-focus-rule); }
.image-info header,
.object-list > header,
.minimap header { justify-content: space-between; height: 27px; }
.info-heading-actions { display: flex; align-items: center; gap: 6px; }
.info-heading-actions button { display: grid; place-items: center; width: 28px; height: 28px; padding: 0; color: var(--vdw-focus-muted); background: transparent; border: 0; cursor: pointer; }
.info-heading-actions button:hover { color: var(--vdw-focus-primary); background: #223b46; }
.object-heading-actions { display: flex; align-items: center; gap: 3px; }
.object-heading-actions button { display: grid; place-items: center; width: 28px; height: 28px; padding: 0; color: var(--vdw-focus-muted); background: transparent; border: 0; cursor: pointer; }
.object-heading-actions button:hover:not(:disabled) { color: var(--vdw-focus-primary); background: #223b46; }
.object-heading-actions button:disabled { color: #61717a; cursor: not-allowed; }
.image-info header strong,
.object-list header strong,
.minimap header strong { font-size: 13px; }
.image-info header span,
.object-list header span,
.minimap header span { color: var(--vdw-focus-muted); font: 13px var(--vdw-mono); }
.image-info dl { display: grid; grid-template-columns: 54px minmax(0, 1fr); gap: 5px 8px; margin: 5px 0 0; font-size: 14px; }
.image-info dt { color: var(--vdw-focus-muted); }
.image-info dd { min-width: 0; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.object-list { overflow-y: auto; padding: 5px 10px; scrollbar-width: none; }
.object-list::-webkit-scrollbar { display: none; }
.empty-copy { margin: 20px 0; color: var(--vdw-focus-muted); font-size: 14px; text-align: center; }
.object-group { margin-top: 5px; background: #1d303a; border: 1px solid var(--vdw-focus-rule); }
.object-group-row { display: grid; grid-template-columns: 15px minmax(0, 1fr) 36px 36px 36px; align-items: center; min-height: 45px; padding: 0 5px 0 8px; }
.object-group-row i { width: 15px; height: 15px; border-radius: 50%; }
.object-group-row button { display: grid; place-items: center; height: 34px; padding: 0; color: var(--vdw-focus-ink); background: transparent; border: 0; cursor: pointer; }
.object-group-row button:not(.group-name) { font-size: 15px; }
.object-group-row .group-name { display: block; overflow: hidden; width: 100%; padding-left: 7px; font-weight: 650; text-align: left; text-overflow: ellipsis; white-space: nowrap; }
.object-group-row span { color: var(--vdw-focus-muted); font: 14px var(--vdw-mono); text-align: center; }
.box-list { border-top: 1px solid var(--vdw-focus-rule); }
.box-item { display: grid; grid-template-columns: minmax(0, 1fr) 28px 28px; min-height: 30px; background: #16262f; border-bottom: 1px solid var(--vdw-focus-rule); }
.box-item.selected { color: var(--vdw-focus-primary); background: #203d3a; }
.box-item > button { display: grid; place-items: center; min-width: 0; padding: 0; color: inherit; background: transparent; border: 0; cursor: pointer; }
.box-item > button:disabled { color: #a8b1b7; cursor: not-allowed; }
.box-item .box-select { grid-template-columns: 27px minmax(0, 1fr); padding: 0 7px; text-align: left; }
.box-list code { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.minimap { padding: 8px 10px 10px; border-top: 1px solid var(--vdw-focus-rule); }
.minimap-image { position: relative; height: 155px; overflow: hidden; background: #17212b; }
.minimap-svg { display: block; width: 100%; height: 100%; }
.viewport-box { fill: rgb(120 210 184 / 8%); stroke: #78d2b8; stroke-width: 2px; filter: drop-shadow(0 0 1px rgb(23 33 43 / 75%)); pointer-events: none; }

.filmstrip { display: grid; grid-column: 2 / 4; grid-row: 3; grid-template-columns: minmax(0, 1fr) 38px; min-width: 0; min-height: 0; background: #18232c; border-top: 1px solid #33414c; }
.filmstrip-scroll { display: flex; align-items: end; gap: 7px; min-width: 0; padding: 8px 8px 9px; overflow-x: scroll; overflow-y: hidden; scrollbar-color: #16866f #111820; scrollbar-gutter: stable; scrollbar-width: thin; }
.filmstrip-scroll::-webkit-scrollbar { height: 10px; }
.filmstrip-scroll::-webkit-scrollbar-track { background: #111820; }
.filmstrip-scroll::-webkit-scrollbar-thumb { background: #16866f; border: 2px solid #111820; border-radius: 5px; }
.filmstrip-scroll::-webkit-scrollbar-thumb:hover { background: #78d2b8; }
.film-frame { position: relative; flex: 0 0 128px; overflow: hidden; padding: 0; background: #111820; border: 2px solid transparent; cursor: pointer; }
.film-frame.current { border-color: #78d2b8; box-shadow: 0 0 0 1px #16866f; }
.filmstrip-actions { display: grid; grid-template-rows: 1fr 1fr; border-left: 1px solid #34434e; }
.filmstrip-actions button { display: grid; place-items: center; padding: 0; color: #b8c5ce; background: #22303a; border: 0; cursor: pointer; }
.filmstrip-actions button + button { border-top: 1px solid #34434e; }
.restore-filmstrip { position: absolute; z-index: 12; bottom: 0; left: calc(50% + 29px); display: flex; align-items: center; gap: 5px; height: 25px; padding: 0 11px; color: #b8c5ce; background: #22303a; border: 1px solid #41515d; border-bottom: 0; border-radius: 4px 4px 0 0; cursor: pointer; transform: translateX(-50%); }
.restore-filmstrip span { font-size: 11px; }

.frame-grid-overlay { position: absolute; inset: 0; z-index: 20; display: grid; grid-template-rows: 48px minmax(0, 1fr); background: #152029; }
.frame-grid-overlay > header { gap: 12px; padding: 0 14px; background: #1e2c36; border-bottom: 1px solid #3a4a56; }
.frame-grid-overlay > header span { color: #91a0ab; font-size: 12px; }
.frame-grid-overlay > header button { display: flex; align-items: center; gap: 5px; margin-left: auto; height: 30px; color: #dbe5eb; background: #283843; border: 1px solid #41515d; }
.frame-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(172px, 1fr)); grid-auto-rows: max-content; gap: 9px; align-content: start; min-height: 0; padding: 12px; overflow: auto; }
.frame-grid button { position: relative; overflow: hidden; padding: 0; color: #d7e0e6; text-align: left; background: #111820; border: 2px solid transparent; }
.frame-grid-card { align-self: start; aspect-ratio: 16 / 9; }
.frame-grid button.current { border-color: #78d2b8; }

.workbench-state { position: absolute; inset: 50px 0 0 58px; z-index: 30; display: grid; place-content: center; gap: 12px; color: #aebbc4; background: #111820; text-align: center; }
.workbench-state.error { color: #f0a39e; }
.workbench-state button { justify-self: center; height: 32px; color: #dce6eb; background: #253640; border: 1px solid #455762; }
.save-overlay { position: fixed; inset: 0; z-index: 3100; display: grid; place-content: center; justify-items: center; gap: 12px; color: #eef5f7; background: rgb(5 9 12 / 68%); animation: save-overlay-in 160ms 100ms both; }
.save-overlay strong { font-size: 14px; font-weight: 600; }
.save-spinner { width: 30px; height: 30px; border: 3px solid rgb(255 255 255 / 22%); border-top-color: #78d2b8; border-radius: 50%; animation: save-spinner 700ms linear infinite; }
:global(.batch-confirm-mask) { background: rgb(4 8 11 / 68%) !important; }
:global(.batch-confirm-dialog) { border: 1px solid #9ba9b2; box-shadow: 0 20px 60px rgb(0 0 0 / 45%); }
@keyframes save-overlay-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes save-spinner { to { transform: rotate(360deg); } }
.shortcut-list { display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 9px 15px; margin: 0; }
.shortcut-list dt { font: 12px var(--vdw-mono); }
.shortcut-list dd { margin: 0; color: #687482; }
.stats-summary { display: grid; gap: 0; margin: 0; }
.stats-summary > div { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: baseline; gap: 20px; min-height: 46px; padding: 9px 4px; border-bottom: 1px solid #e1e6e9; }
.stats-summary > div:last-child { border-bottom: 0; }
.stats-summary dt { color: #687482; }
.stats-summary dd { margin: 0; color: var(--vdw-teal); font: 700 20px var(--vdw-mono); }
.model-registration-form { display: grid; gap: 14px; }
.model-registration-form > label { display: grid; grid-template-columns: 92px minmax(0, 1fr); align-items: center; gap: 12px; }
.model-registration-form > label > span { color: #5f6c76; font-size: 13px; }
.model-registration-form > p { margin: 0; color: #687482; font-size: 13px; }
.xanylabeling-settings-form { display: grid; gap: 16px; }
.xanylabeling-settings-form > label { display: grid; gap: 7px; }
.xanylabeling-settings-form > label > span { color: #5f6c76; font-size: 13px; }

@media (max-width: 1180px) {
  .annotation-workbench { grid-template-columns: 54px minmax(0, 1fr) 250px; }
  .auto-controls label { display: none; }
  .category-select { width: 260px; }
}

@media (prefers-reduced-motion: reduce) {
  .annotation-workbench *,
  .annotation-focus-tools * { scroll-behavior: auto !important; transition: none !important; }
  .save-overlay,
  .save-spinner { animation: none !important; }
}
</style>
