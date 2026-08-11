<script setup lang="ts">
import {
  Aim, Download, Filter, Scissor, Setting, Upload, VideoPlay,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError } from '../api/auth'
import {
  createExtractions,
  listVideos,
  setVideoEnabled,
  setVideosEnabledByAnnotation,
  videoContentUrl,
  videoThumbnailUrl,
  type ImportBatch,
  type PlanBatch,
  type Video,
} from '../api/media'
import type { Project } from '../api/projects'
import ExtractionConfirmDialog from '../components/ExtractionConfirmDialog.vue'
import BatchAnnotationDialog from '../components/BatchAnnotationDialog.vue'
import ExportDatasetDialog from '../components/ExportDatasetDialog.vue'
import FramesDialog from '../components/FramesDialog.vue'
import ImportVideosDialog from '../components/ImportVideosDialog.vue'
import SamplingDialog from '../components/SamplingDialog.vue'
import VButton from '../ui/VButton.vue'
import VTag from '../ui/VTag.vue'
import { videoTone } from '../ui/status'
import { videoWorkflowStatus } from './videoStatus'
import { useProjectHeaderHost } from '../ui/projectHeaderHost'

const props = defineProps<{ project: Project }>()
const router = useRouter()
const projectId = props.project.id
const videos = ref<Video[]>([])
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const loading = ref(false)
const importOpen = ref(false)
const exportOpen = ref(false)
const playing = ref<Video | null>(null)
const frameVideo = ref<Video | null>(null)
const selected = ref<string[]>([])
const samplingOpen = ref(false)
const samplingTargets = ref<Video[]>([])
const configureChoiceTargets = ref<Video[]>([])
const extractionChoiceTargets = ref<Video[]>([])
const extractionTargets = ref<Video[]>([])
const extractionConfirmOpen = ref(false)
const annotationOpen = ref(false)
const annotationTargets = ref<Video[]>([])
const annotationChoiceTargets = ref<Video[]>([])
const annotationScope = ref<'unannotated' | 'all'>('unannotated')
const enabledByAnnotationTargets = ref<Video[]>([])
const enabledByAnnotationConfirmTargets = ref<Video[]>([])
const enabledByAnnotationCountdown = ref(3)
let enabledByAnnotationTimer: number | undefined
const changingEnabled = ref('')
const error = ref('')

const canEdit = computed(() => props.project.role === 'owner' || props.project.role === 'editor')
const importLimitReached = computed(() => total.value >= 999)
const enabledOnPage = computed(() => videos.value.filter((video) => video.enabled).length)
const selectableIds = computed(() =>
  canEdit.value ? videos.value.filter((video) => video.status === 'ready').map((video) => video.id) : [],
)
const selectedOnPage = computed(() =>
  selected.value.filter((id) => selectableIds.value.includes(id)),
)
const selectedVideos = computed(() =>
  videos.value.filter((video) => selected.value.includes(video.id)),
)
const selectedCounts = computed(() => ({
  configured: selectedVideos.value.filter((video) => video.sampling !== null).length,
  extracted: selectedVideos.value.filter((video) => (video.sampling?.extracted_frames ?? 0) > 0).length,
  screened: selectedVideos.value.filter((video) => (video.sampling?.frame_revision ?? 0) > 1).length,
  annotated: selectedVideos.value.filter((video) => video.has_annotations).length,
}))
const allSelected = computed(
  () => selectableIds.value.length > 0 && selectedOnPage.value.length === selectableIds.value.length,
)
const someSelected = computed(
  () => selectedOnPage.value.length > 0 && !allSelected.value,
)
const statusLabels = { pending: '等待导入', ready: '可用', unavailable: '不可用' } as const

function duration(seconds: number) {
  const rounded = Math.max(0, Math.round(seconds))
  const hours = Math.floor(rounded / 3600)
  const minutes = Math.floor((rounded % 3600) / 60)
  const rest = rounded % 60
  return hours
    ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

function fileSize(bytes: number) {
  if (!bytes) return '—'
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

function hideBrokenThumbnail(event: Event) {
  const image = event.target as HTMLImageElement
  image.style.display = 'none'
}

async function load(
  nextPage = page.value,
  nextPageSize = pageSize.value,
  preserveSelection = false,
) {
  loading.value = true
  error.value = ''
  try {
    const videoResult = await listVideos(projectId, nextPage, nextPageSize)
    videos.value = videoResult.items
    selected.value = preserveSelection
      ? selected.value.filter((id) => videoResult.items.some((video) => video.id === id))
      : []
    page.value = videoResult.page
    pageSize.value = videoResult.page_size
    total.value = videoResult.total
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '视频工作区加载失败'
  } finally {
    loading.value = false
  }
}

function changePageSize(event: Event) {
  const nextPageSize = Number((event.target as HTMLSelectElement).value)
  void load(1, nextPageSize)
}

function toggleCurrentPage(checked: boolean) {
  selected.value = checked ? [...selectableIds.value] : []
}

function toggleVideo(video: Video, checked: boolean) {
  selected.value = checked
    ? [...new Set([...selected.value, video.id])]
    : selected.value.filter((id) => id !== video.id)
}

async function changeVideoEnabled(video: Video, enabled: boolean) {
  changingEnabled.value = video.id
  error.value = ''
  try {
    await setVideoEnabled(projectId, video.id, enabled, video.version)
    ElMessage.success(enabled ? '视频已启用。' : '视频已停用；仍可播放和管理采样。')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '视频启停状态修改失败')
    if (reason instanceof ApiError && reason.status === 409) await load()
  } finally {
    changingEnabled.value = ''
  }
}

function imported(batch: ImportBatch) {
  ElMessage.success(`已创建 ${batch.accepted.length} 个任务，跳过 ${batch.skipped.length} 项，拒绝 ${batch.rejected.length} 项。`)
  void load(1)
}

function targets(videoIds: string[]) {
  return videos.value.filter((video) => videoIds.includes(video.id))
}

function openSampling(targetVideos: Video[]) {
  samplingTargets.value = targetVideos
  samplingOpen.value = true
}

function configure(videoIds: string[]) {
  const targetVideos = targets(videoIds)
  if (targetVideos.length > 1 && targetVideos.some((video) => video.sampling)) {
    configureChoiceTargets.value = targetVideos
    return
  }
  openSampling(targetVideos)
}

function configureUnconfigured() {
  const safe = configureChoiceTargets.value.filter((video) => !video.sampling)
  configureChoiceTargets.value = []
  if (safe.length) openSampling(safe)
}

function configureAll() {
  const targetVideos = configureChoiceTargets.value
  configureChoiceTargets.value = []
  openSampling(targetVideos)
}

function openAnnotation(video: Video) {
  if (!canEdit.value || !video.sampling?.extracted_frames) return
  void router.push(`/projects/${projectId}/videos/${video.id}/annotation`)
}

function openBatchAnnotation() {
  const targetVideos = selectedVideos.value
  if (targetVideos.some((video) => video.has_annotations)) {
    annotationChoiceTargets.value = targetVideos
    return
  }
  openBatchAnnotationSettings(targetVideos, 'unannotated')
}

function openBatchAnnotationSettings(targetVideos: Video[], scope: 'unannotated' | 'all') {
  annotationChoiceTargets.value = []
  annotationTargets.value = scope === 'unannotated'
    ? targetVideos.filter((video) => !video.has_annotations)
    : targetVideos
  annotationScope.value = scope
  annotationOpen.value = true
}

function annotationSubmitted(accepted: string[]) {
  selected.value = selected.value.filter((id) => !accepted.includes(id))
  void load(page.value, pageSize.value, true)
}

function openEnabledByAnnotation() {
  const targetVideos = selectedVideos.value
  if (!targetVideos.some((video) => video.has_annotations)) {
    ElMessage.warning('所选视频均无标注，按标注启停不会产生有效结果。')
    return
  }
  enabledByAnnotationTargets.value = targetVideos
}

function isScreened(video: Video) {
  return (video.sampling?.frame_revision ?? 0) > 1
}

function clearEnabledByAnnotationTimer() {
  if (enabledByAnnotationTimer !== undefined) window.clearInterval(enabledByAnnotationTimer)
  enabledByAnnotationTimer = undefined
}

function closeEnabledByAnnotationConfirmation() {
  clearEnabledByAnnotationTimer()
  enabledByAnnotationConfirmTargets.value = []
  enabledByAnnotationCountdown.value = 3
}

function confirmAllEnabledByAnnotation() {
  enabledByAnnotationConfirmTargets.value = [...enabledByAnnotationTargets.value]
  enabledByAnnotationTargets.value = []
  enabledByAnnotationCountdown.value = 3
  clearEnabledByAnnotationTimer()
  enabledByAnnotationTimer = window.setInterval(() => {
    if (enabledByAnnotationCountdown.value <= 1) {
      enabledByAnnotationCountdown.value = 0
      clearEnabledByAnnotationTimer()
    } else {
      enabledByAnnotationCountdown.value -= 1
    }
  }, 1000)
}

function submitUnscreenedEnabledByAnnotation() {
  const targets = enabledByAnnotationTargets.value.filter(
    (video) => video.has_annotations && !isScreened(video),
  )
  void submitEnabledByAnnotation(targets, 'unscreened-only')
}

async function submitEnabledByAnnotation(targetVideos: Video[], scope: 'unscreened-only' | 'all') {
  try {
    const result = await setVideosEnabledByAnnotation(
      projectId,
      targetVideos.map((video) => video.id),
      scope,
      scope === 'all',
      Object.fromEntries(targetVideos.map((video) => [video.id, video.version])),
    )
    const ignored = result.rejected.filter((item) => item.code === 'no_annotations').length
    ElMessage.success(
      ignored
        ? `已更新 ${result.accepted.length} 个视频，忽略 ${ignored} 个无标注视频。`
        : `已更新 ${result.accepted.length} 个视频的启停状态。`,
    )
    enabledByAnnotationTargets.value = []
    closeEnabledByAnnotationConfirmation()
    selected.value = selected.value.filter((id) => !result.accepted.some((item) => item.video_id === id))
    await load(page.value, pageSize.value, true)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '按标注启停失败')
  }
}

/**
 * 后端逐个视频校验采样参数，非法值会进 rejected 而不是抛错。
 * 这里过去无条件弹"采样方案已保存"，于是填了非法值也提示成功——用户以为
 * 存上了，实际一个都没存。现在按 accepted / rejected 分别播报。
 */
async function samplingSubmitted(batch: PlanBatch) {
  if (!batch.accepted.length) {
    ElMessage.error(batch.rejected[0]?.reason
      ? `采样方案未保存：${batch.rejected[0].reason}`
      : '采样方案未保存。')
  } else if (batch.rejected.length) {
    ElMessage.warning(
      `已保存 ${batch.accepted.length} 个视频的采样方案，${batch.rejected.length} 个未通过校验。`,
    )
  } else {
    ElMessage.success('采样方案已保存。')
  }
  const accepted = new Set(batch.accepted.map((item) => item.video_id))
  selected.value = selected.value.filter((id) => !accepted.has(id))
  await load(page.value, pageSize.value, true)
}

function openExtractionConfirmation(targetVideos: Video[]) {
  extractionTargets.value = targetVideos
  extractionConfirmOpen.value = true
}

function extract(videoIds: string[]) {
  const targetVideos = targets(videoIds)
  if (!targetVideos.some((video) => (video.sampling?.extracted_frames ?? 0) > 0)) {
    void submitExtraction(targetVideos, 'none')
    return
  }
  if (targetVideos.length > 1) {
    extractionChoiceTargets.value = targetVideos
    return
  }
  openExtractionConfirmation(targetVideos)
}

function extractUnextracted() {
  const safe = extractionChoiceTargets.value.filter(
    (video) => (video.sampling?.extracted_frames ?? 0) === 0,
  )
  extractionChoiceTargets.value = []
  if (safe.length) void submitExtraction(safe, 'none')
}

function extractAll() {
  const targetVideos = extractionChoiceTargets.value
  extractionChoiceTargets.value = []
  openExtractionConfirmation(targetVideos)
}

async function submitExtraction(
  targetVideos: Video[],
  overwriteLevel: 'none' | 'light' | 'destructive',
) {
  error.value = ''
  try {
    const batch = await createExtractions(
      projectId,
      targetVideos.map((video) => video.id),
      overwriteLevel,
    )
    if (batch.rejected.length) {
      const riskChanged = batch.rejected.some((item) =>
        item.code === 'light_overwrite_required'
        || item.code === 'destructive_overwrite_required',
      )
      ElMessage.warning(
        riskChanged
          ? `已创建 ${batch.accepted.length} 个任务；部分视频风险状态已变化，请按最新状态重新确认。`
          : `已创建 ${batch.accepted.length} 个任务，拒绝 ${batch.rejected.length} 项。`,
      )
    } else {
      ElMessage.success(`已创建 ${batch.accepted.length} 个抽帧任务。`)
    }
    const accepted = new Set(batch.accepted.map((item) => item.video_id))
    selected.value = selected.value.filter((id) => !accepted.has(id))
    await load(page.value, pageSize.value, true)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '抽帧任务创建失败')
  }
}

function refreshAfterTask() {
  void load()
}

onMounted(() => {
  void load()
  window.addEventListener('vdm:tasks-settled', refreshAfterTask)
})
onUnmounted(() => {
  window.removeEventListener('vdm:tasks-settled', refreshAfterTask)
  clearEnabledByAnnotationTimer()
})

const headerHost = useProjectHeaderHost()
</script>

<template>
  <main class="workbench-shell">
    <section class="workspace">
        <!-- 视频总数与启用数是本页的统计，送进 header 的副信息位，页内不再重复 -->
        <Teleport defer :disabled="!headerHost" to="#project-page-meta">
          <span data-test="page-stat">{{ total }} 个视频 · {{ enabledOnPage }} 个已启用</span>
        </Teleport>

        <!-- 导出数据集与导入视频只作用于本页的原始数据，因此放在页内工具行而不是
             项目级 header：否则用户切到标签管理、数据集管理时按钮会凭空消失。 -->
        <section class="video-action-lane" data-test="video-action-lane">
          <template v-if="canEdit && selected.length">
            <strong class="selection-summary">
              已选择 {{ selected.length }} 个视频
              <small>
                已配置 {{ selectedCounts.configured }} · 已抽帧 {{ selectedCounts.extracted }} ·
                已筛帧 {{ selectedCounts.screened }} · 有标注 {{ selectedCounts.annotated }}
              </small>
            </strong>
            <div>
            <VButton variant="default" data-test="batch-configure" @click="configure(selected)">批量配置采样</VButton>
            <VButton variant="default" data-test="batch-extract" @click="extract(selected)">批量抽帧</VButton>
            <VButton variant="default" data-test="batch-auto-annotate" @click="openBatchAnnotation">批量自动标注</VButton>
            <VButton variant="default" data-test="batch-enabled-by-annotation" @click="openEnabledByAnnotation">按标注启停</VButton>
            </div>
          </template>
          <template v-else-if="canEdit">
            <span class="lane-hint">勾选视频后可批量配置采样、抽帧与自动标注。</span>
            <div class="workspace-toolbar-actions" data-test="video-toolbar-actions">
              <VButton data-test="export-dataset" @click="exportOpen = true">
                <template #icon><el-icon><Download /></el-icon></template>
                导出数据集
              </VButton>
              <VButton
                data-test="import-videos"
                variant="primary"
                :disabled="importLimitReached"
                :title="importLimitReached ? '项目视频数量已达上限（999）' : '导入视频'"
                @click="importOpen = true"
              >
                <template #icon><el-icon><Upload /></el-icon></template>
                导入视频
              </VButton>
            </div>
          </template>
        </section>

        <section v-loading="loading" class="video-ledger">
          <div v-if="error" class="state-panel state-panel--error">{{ error }}</div>
          <div v-if="videos.length" class="ledger-scroll">
            <header class="ledger-row ledger-head">
              <span class="selection-cell">
                <el-checkbox
                  v-if="canEdit"
                  data-test="select-all"
                  aria-label="选择当前页全部可操作视频"
                  :model-value="allSelected"
                  :indeterminate="someSelected"
                  :disabled="!selectableIds.length"
                  @change="toggleCurrentPage(Boolean($event))"
                />
              </span>
              <span>启用</span>
              <span>视频</span>
              <span>来源</span>
              <span>规格</span>
              <span>启用/总数</span>
              <span>状态</span>
              <span>业务状态</span>
              <span>操作</span>
            </header>

            <article
              v-for="video in videos"
              :key="video.id"
              class="ledger-row media-row"
              :data-status="video.status"
              :data-enabled="video.enabled"
            >
              <span class="selection-cell">
                <el-checkbox
                  v-if="canEdit"
                  :data-test="`select-${video.id}`"
                  aria-label="选择视频"
                  :model-value="selected.includes(video.id)"
                  :disabled="video.status !== 'ready'"
                  @change="toggleVideo(video, Boolean($event))"
                />
              </span>
              <span class="enabled-cell">
                <el-switch
                  v-if="canEdit"
                  :data-test="`enabled-${video.id}`"
                  :model-value="video.enabled"
                  :loading="changingEnabled === video.id"
                  :aria-label="`${video.enabled ? '停用' : '启用'}视频 ${video.title}`"
                  @change="changeVideoEnabled(video, Boolean($event))"
                />
                <span v-else class="readonly-enabled" :data-enabled="video.enabled">
                  {{ video.enabled ? '启用' : '停用' }}
                </span>
              </span>
              <div class="media-identity">
                <div class="thumbnail">
                  <img
                    v-if="video.status === 'ready'"
                    :src="videoThumbnailUrl(projectId, video.id)"
                    alt=""
                    @error="hideBrokenThumbnail"
                  />
                  <code>{{ video.short_code }}</code>
                </div>
                <div>
                  <strong :title="video.title">{{ video.title }}</strong>
                  <p :title="video.source_name || video.source_url || ''">
                    {{ video.source_name || video.source_url || '等待 Worker 解析来源' }}
                  </p>
                </div>
              </div>
              <span class="source-mark">{{ video.source_type === 'local' ? 'LOCAL' : 'REMOTE' }}</span>
              <div class="media-spec">
                <span>{{ video.width && video.height ? `${video.width}×${video.height}` : '—' }}</span>
                <small>{{ duration(video.duration) }} · {{ fileSize(video.file_size) }}</small>
              </div>
              <span class="frame-count">
                {{ video.sampling ? `${video.sampling.enabled_frames}/${video.sampling.extracted_frames || video.sampling.expected_frames}` : '—' }}
              </span>
              <VTag :tone="video.status === 'ready' ? 'ok' : video.status === 'unavailable' ? 'danger' : 'idle'">
                {{ statusLabels[video.status] }}
              </VTag>
              <div class="status-info" :title="videoWorkflowStatus(video).detail">
                <VTag :tone="videoTone(videoWorkflowStatus(video).code)">
                  {{ videoWorkflowStatus(video).primary }}
                </VTag>
                <VTag
                  v-for="flag in videoWorkflowStatus(video).flags"
                  :key="flag"
                  :tone="flag === '视频停用' ? 'danger' : 'idle'"
                >{{ flag }}</VTag>
                <small v-if="videoWorkflowStatus(video).detail" class="status-detail">
                  {{ videoWorkflowStatus(video).detail }}
                </small>
              </div>
              <div class="row-actions">
                <VButton
                  variant="quiet"
                  size="sm"
                  :data-test="`play-${video.id}`"
                  :disabled="video.status !== 'ready'"
                  @click="playing = video"
                ><template #icon><el-icon><VideoPlay /></el-icon></template>播放</VButton>
                <VButton
                  v-if="canEdit"
                  :variant="!video.sampling ? 'default' : 'quiet'"
                  size="sm"
                  :data-test="`configure-${video.id}`"
                  :disabled="video.status !== 'ready'"
                  @click="configure([video.id])"
                ><template #icon><el-icon><Setting /></el-icon></template>采样</VButton>
                <VButton
                  v-if="canEdit"
                  :variant="video.sampling && !video.sampling.extracted_frames ? 'default' : 'quiet'"
                  size="sm"
                  :data-test="`extract-${video.id}`"
                  :disabled="!video.sampling"
                  @click="extract([video.id])"
                ><template #icon><el-icon><Scissor /></el-icon></template>抽帧</VButton>
                <VButton
                  variant="quiet"
                  size="sm"
                  :data-test="`annotate-${video.id}`"
                  :disabled="!canEdit || !video.sampling?.extracted_frames"
                  @click="openAnnotation(video)"
                ><template #icon><el-icon><Aim /></el-icon></template>标注</VButton>
                <VButton
                  variant="quiet"
                  size="sm"
                  :data-test="`frames-${video.id}`"
                  :disabled="!video.sampling?.extracted_frames"
                  @click="frameVideo = video"
                ><template #icon><el-icon><Filter /></el-icon></template>筛帧</VButton>
              </div>
            </article>
          </div>

          <div v-if="!loading && !videos.length" class="empty-state">
            <h2>项目中还没有视频</h2>
            <p>{{ canEdit ? '从本地目录或远程 URL 创建第一批导入任务。' : '项目编辑者导入视频后会显示在这里。' }}</p>
            <VButton variant="primary" v-if="canEdit" @click="importOpen = true">导入视频</VButton>
          </div>

          <footer v-if="total" class="ledger-footer">
            <label>
              每页
              <select data-test="page-size" :value="pageSize" @change="changePageSize">
                <option :value="25">25</option>
                <option :value="50">50</option>
                <option :value="100">100</option>
                <option :value="200">200</option>
                <option :value="999">全部</option>
              </select>
            </label>
            <el-pagination
              layout="prev, pager, next"
              :current-page="page"
              :page-size="pageSize"
              :total="total"
              @current-change="load($event, pageSize)"
            />
          </footer>
        </section>
    </section>

    <el-dialog
      append-to-body
      :model-value="playing !== null"
      :title="playing?.title"
      width="min(960px, calc(100vw - 32px))"
      @update:model-value="!$event && (playing = null)"
    >
      <video v-if="playing" controls preload="metadata" :src="videoContentUrl(projectId, playing.id)" />
    </el-dialog>

    <ImportVideosDialog
      v-if="canEdit && !importLimitReached"
      v-model="importOpen"
      :project-id="projectId"
      @submitted="imported"
    />
    <ExportDatasetDialog
      v-if="canEdit"
      v-model="exportOpen"
      :project-id="projectId"
    />
    <SamplingDialog
      v-if="canEdit"
      v-model="samplingOpen"
      :project-id="projectId"
      :videos="samplingTargets"
      @submitted="samplingSubmitted"
    />
    <BatchAnnotationDialog
      v-if="canEdit"
      v-model="annotationOpen"
      :project-id="projectId"
      :videos="annotationTargets"
      :scope="annotationScope"
      @submitted="annotationSubmitted"
    />
    <el-dialog
      append-to-body
      :model-value="annotationChoiceTargets.length > 0"
      title="批量自动标注"
      width="min(560px, calc(100vw - 32px))"
      @update:model-value="!$event && (annotationChoiceTargets = [])"
    >
      <p>
        选中的视频中有
        {{ annotationChoiceTargets.filter((video) => video.has_annotations).length }} 个已有标注。
        请选择本次处理范围。
      </p>
      <template #footer>
        <VButton variant="default" @click="annotationChoiceTargets = []">取消</VButton>
        <VButton variant="default" data-test="annotation-unannotated-only"
          :disabled="!annotationChoiceTargets.some((video) => !video.has_annotations)"
          @click="openBatchAnnotationSettings(annotationChoiceTargets, 'unannotated')"
        >仅处理 {{ annotationChoiceTargets.filter((video) => !video.has_annotations).length }} 个未标注视频</VButton>
        <VButton variant="danger" data-test="annotation-all"
          @click="openBatchAnnotationSettings(annotationChoiceTargets, 'all')">处理全部 {{ annotationChoiceTargets.length }} 个视频</VButton>
      </template>
    </el-dialog>
    <el-dialog
      append-to-body
      :model-value="enabledByAnnotationTargets.length > 0"
      title="按标注启停"
      width="min(620px, calc(100vw - 32px))"
      @update:model-value="!$event && (enabledByAnnotationTargets = [])"
    >
      <el-alert
        title="无标注视频将被忽略"
        description="无标注的视频即使已经手动筛帧，执行按标注启停也只会停用全部采样帧，因此不会处理。"
        type="info"
        show-icon
        :closable="false"
      />
      <div class="annotation-scope-summary">
        <div><strong>{{ enabledByAnnotationTargets.filter((video) => video.has_annotations && !isScreened(video)).length }}</strong><span>有标注 · 未筛帧</span></div>
        <div><strong>{{ enabledByAnnotationTargets.filter((video) => video.has_annotations && isScreened(video)).length }}</strong><span>有标注 · 已筛帧</span></div>
        <div><strong>{{ enabledByAnnotationTargets.filter((video) => !video.has_annotations && !isScreened(video)).length }}</strong><span>无标注 · 未筛帧</span></div>
        <div><strong>{{ enabledByAnnotationTargets.filter((video) => !video.has_annotations && isScreened(video)).length }}</strong><span>无标注 · 已筛帧</span></div>
      </div>
      <template #footer>
        <VButton variant="default" @click="enabledByAnnotationTargets = []">取消</VButton>
        <VButton variant="default" data-test="enabled-by-annotation-unscreened"
          :disabled="!enabledByAnnotationTargets.some((video) => video.has_annotations && !isScreened(video))"
          @click="submitUnscreenedEnabledByAnnotation"
        >仅处理 {{ enabledByAnnotationTargets.filter((video) => video.has_annotations && !isScreened(video)).length }} 个未筛帧视频</VButton>
        <VButton variant="danger" data-test="enabled-by-annotation-all"
          @click="confirmAllEnabledByAnnotation">处理全部 {{ enabledByAnnotationTargets.filter((video) => video.has_annotations).length }} 个有标注视频</VButton>
      </template>
    </el-dialog>
    <el-dialog
      append-to-body
      :model-value="enabledByAnnotationConfirmTargets.length > 0"
      title="确认覆盖现有筛帧结果"
      width="min(560px, calc(100vw - 32px))"
      @update:model-value="!$event && closeEnabledByAnnotationConfirmation()"
    >
      <el-alert
        title="此操作会覆盖已有的手动筛帧结果"
        :description="`将对 ${enabledByAnnotationConfirmTargets.filter((video) => video.has_annotations).length} 个有标注视频重新按标注启停；${enabledByAnnotationConfirmTargets.filter((video) => !video.has_annotations).length} 个无标注视频仍会被忽略。`"
        type="error"
        show-icon
        :closable="false"
      />
      <template #footer>
        <VButton variant="default" @click="closeEnabledByAnnotationConfirmation">取消</VButton>
        <VButton variant="danger" data-test="enabled-by-annotation-confirm"
          :disabled="enabledByAnnotationCountdown> 0"
          @click="submitEnabledByAnnotation(enabledByAnnotationConfirmTargets, 'all')"
        >{{ enabledByAnnotationCountdown > 0 ? `确认覆盖（${enabledByAnnotationCountdown} 秒）` : '确认覆盖筛帧结果' }}</VButton>
      </template>
    </el-dialog>
    <el-dialog
      append-to-body
      :model-value="configureChoiceTargets.length > 0"
      title="批量配置采样"
      width="min(540px, calc(100vw - 32px))"
      @update:model-value="!$event && (configureChoiceTargets = [])"
    >
      <p>选中的视频中已有 {{ configureChoiceTargets.filter((video) => video.sampling).length }} 个配置过采样方案。</p>
      <template #footer>
        <VButton variant="default" @click="configureChoiceTargets = []">取消</VButton>
        <VButton variant="default" data-test="configure-unconfigured"
          :disabled="!configureChoiceTargets.some((video) => !video.sampling)"
          @click="configureUnconfigured"
        >仅处理 {{ configureChoiceTargets.filter((video) => !video.sampling).length }} 个未配置视频</VButton>
        <VButton variant="default" data-test="configure-all" @click="configureAll">
          处理全部 {{ configureChoiceTargets.length }} 个视频
        </VButton>
      </template>
    </el-dialog>
    <el-dialog
      append-to-body
      :model-value="extractionChoiceTargets.length > 0"
      title="批量抽帧"
      width="min(540px, calc(100vw - 32px))"
      @update:model-value="!$event && (extractionChoiceTargets = [])"
    >
      <p>选中的视频中已有 {{ extractionChoiceTargets.filter((video) => video.sampling?.extracted_frames).length }} 个完成抽帧。</p>
      <template #footer>
        <VButton variant="default" @click="extractionChoiceTargets = []">取消</VButton>
        <VButton variant="default" data-test="extract-unextracted"
          :disabled="!extractionChoiceTargets.some((video) => !video.sampling?.extracted_frames)"
          @click="extractUnextracted"
        >仅处理 {{ extractionChoiceTargets.filter((video) => !video.sampling?.extracted_frames).length }} 个未抽帧视频</VButton>
        <VButton variant="danger" data-test="extract-all" @click="extractAll">
          处理全部 {{ extractionChoiceTargets.length }} 个视频
        </VButton>
      </template>
    </el-dialog>
    <ExtractionConfirmDialog
      v-model="extractionConfirmOpen"
      :videos="extractionTargets"
      @confirmed="submitExtraction(extractionTargets, $event)"
    />
    <FramesDialog
      :model-value="frameVideo !== null"
      :project-id="projectId"
      :video-id="frameVideo?.id || ''"
      :short-code="frameVideo?.short_code || ''"
      :title="frameVideo?.title || ''"
      :can-edit="canEdit"
      :image-width="frameVideo?.width || 0"
      :image-height="frameVideo?.height || 0"
      @update:model-value="!$event && (frameVideo = null)"
      @updated="load()"
    />
  </main>
</template>

<style scoped>
.annotation-scope-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.annotation-scope-summary > div {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}

.annotation-scope-summary strong { font: 700 22px var(--vdw-mono); }
.annotation-scope-summary span { color: var(--el-text-color-secondary); font-size: 14px; }

.workbench-shell {
  min-height: 100%;
  color: var(--vdw-ink);
  background: var(--vdw-app);
}

.workspace {
  min-width: 0;
  padding: 0 18px 26px;
}

.workspace :deep(.page-header) {
  margin: 0 -18px 18px;
}

.workspace-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 页内工具行：未勾选时左侧是操作提示、右侧是页面动作；勾选后整行切换为
   批量动作。同一位置同一语义（"对当前列表做什么"），不会出现两排按钮。 */
.video-action-lane {
  display: flex;
  align-items: center;
  gap: 13px;
  justify-content: flex-start;
  min-height: 52px;
  padding: 0 9px;
  color: var(--vdw-ink-2);
  font-size: 14px;
  border-bottom: 1px solid var(--vdw-line);
}

.lane-hint {
  color: var(--vdw-ink-3);
}

.video-action-lane > div {
  display: flex;
  gap: 7px;
  margin-left: auto;
}

.selection-summary {
  display: flex;
  align-items: baseline;
  gap: 12px;
  color: var(--vdw-ink);
}

.selection-summary small {
  color: var(--vdw-ink-2);
  font-size: 14px;
  font-weight: 400;
}

.video-ledger {
  margin-top: 9px;
  background: white;
  border: 1px solid var(--vdw-line);
}

.ledger-scroll {
  overflow-x: auto;
}

.ledger-row {
  display: grid;
  /* 来源/状态/启用总数三列原为 40/50/80px，表头文字被压得换行。
     按内容需要的最小宽度给足，宁可挤压弹性列也不让表头折行。
     末列 344px 是 5 个"图标+文字"操作的实测所需宽度；给少了会撑破网格
     并在台账里产生横向滚动。 */
  grid-template-columns:
    30px 50px minmax(180px, 1.2fr) 62px 100px 96px 62px
    minmax(180px, 1.1fr) 344px;
  gap: 8px;
  align-items: center;
  /* 固定列合计 + 两个弹性列的下限；小于此宽度时才允许台账横向滚动 */
  min-width: 1348px;
  /* 与 VRow 保持一致的行内呼吸空间 */
  padding: 12px 12px;
}

/* 全列左对齐：居中列会让每列的视觉起点各不相同，扫读时眼睛要来回找。
   列间距由 grid 的 gap 负责，不靠单元格内的对齐制造间隔。 */
.ledger-row > * {
  justify-self: start;
  text-align: left;
}

.ledger-head {
  height: 40px;
  padding-top: 0;
  padding-bottom: 0;
  color: var(--vdw-ink-2);
  font-size: 14px;
  white-space: nowrap;
  background: var(--vdw-surface-2);
  border-bottom: 1px solid var(--vdw-line);
}

/* 数据行同样全列左对齐，与表头保持同一起点（见 .ledger-row > *） */

.media-row {
  position: relative;
  min-height: var(--vdw-row-height);
  border-bottom: 1px solid var(--vdw-line);
}

.media-row:last-child {
  border-bottom: 0;
}

.media-row::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: #9ba8b4;
  content: '';
}

.media-row[data-status='ready']::before {
  background: var(--vdw-accent);
}

.media-row[data-status='unavailable']::before {
  background: #c74c46;
}

.media-row[data-enabled='false'] {
  color: #65717c;
  background: var(--vdw-surface-2);
}

.selection-cell,
.enabled-cell {
  display: grid;
  place-items: center;
}

.selection-cell :deep(.el-checkbox) {
  height: 22px;
}

.enabled-cell :deep(.el-switch) {
  --el-switch-on-color: var(--vdw-accent);
}

.readonly-enabled {
  color: var(--vdw-ink-2);
  font-size: 14px;
}

.readonly-enabled[data-enabled='false'] {
  color: #a33e39;
}

.media-identity {
  display: grid;
  grid-template-columns: 79px minmax(0, 1fr);
  gap: 9px;
  align-items: center;
  min-width: 0;
}

.thumbnail {
  position: relative;
  width: 79px;
  height: 46px;
  overflow: hidden;
  background: linear-gradient(135deg, #1f2c38, #344556);
}

.thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumbnail code {
  position: absolute;
  right: 2px;
  bottom: 2px;
  padding: 1px 2px;
  color: #c9fff0;
  font: 13px var(--vdw-mono);
  background: rgb(13 23 32 / 72%);
}

.media-identity strong,
.media-identity p {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.media-identity strong {
  margin-bottom: 3px;
  font-size: 15px;
}

.media-identity p {
  margin: 0;
  color: var(--vdw-ink-2);
  font-size: 14px;
}

.source-mark {
  width: fit-content;
  padding: 2px 4px;
  color: #315d78;
  font: 14px var(--vdw-mono);
  border: 1px solid #a8bfcd;
}

.media-spec {
  display: grid;
  gap: 2px;
  font-size: 13px;
}

.media-spec small {
  color: var(--vdw-ink-2);
  font-size: 13px;
}

.frame-count {
  font: 13px var(--vdw-mono);
}

.status-info {
  display: flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
  gap: 4px;
  color: #53616d;
  font-size: 14px;
  white-space: nowrap;
}

.status-info :deep(.vdw-tag) {
  flex: 0 0 auto;
}

.status-detail {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--vdw-ink-2);
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 行操作左对齐，与其它列同一起点（4.1）。原为 flex-end，操作列孤零零贴右边，
   与左对齐的表头对不上。 */
.row-actions {
  display: flex;
  gap: 2px;
}

.ledger-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 46px;
  padding: 4px 9px 4px 13px;
  border-top: 1px solid var(--vdw-line);
}

.ledger-footer label {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--vdw-ink-2);
  font-size: 14px;
}

.ledger-footer select {
  height: 29px;
  padding: 0 24px 0 8px;
  color: var(--vdw-ink);
  background: white;
  border: 1px solid #bfc8d0;
}

.empty-state {
  padding: 53px 26px;
  text-align: center;
}

.empty-state h2 {
  margin: 0 0 7px;
  font: 700 22px var(--vdw-sans);
}

.empty-state p {
  margin: 0 0 16px;
  color: var(--vdw-ink-2);
  font-size: 14px;
}

video {
  display: block;
  width: 100%;
  max-height: 70vh;
  background: #0d171f;
}

</style>
