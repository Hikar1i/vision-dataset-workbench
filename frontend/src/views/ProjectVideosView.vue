<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError } from '../api/auth'
import {
  createExtractions,
  listVideos,
  setVideoEnabled,
  videoContentUrl,
  videoThumbnailUrl,
  type ImportBatch,
  type Video,
} from '../api/media'
import type { Project } from '../api/projects'
import ExtractionConfirmDialog from '../components/ExtractionConfirmDialog.vue'
import FramesDialog from '../components/FramesDialog.vue'
import ImportVideosDialog from '../components/ImportVideosDialog.vue'
import SamplingDialog from '../components/SamplingDialog.vue'
import { videoWorkflowStatus } from './videoStatus'

const props = defineProps<{ project: Project }>()
const router = useRouter()
const projectId = props.project.id
const videos = ref<Video[]>([])
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const loading = ref(false)
const importOpen = ref(false)
const playing = ref<Video | null>(null)
const frameVideo = ref<Video | null>(null)
const selected = ref<string[]>([])
const samplingOpen = ref(false)
const samplingTargets = ref<Video[]>([])
const configureChoiceTargets = ref<Video[]>([])
const extractionChoiceTargets = ref<Video[]>([])
const extractionTargets = ref<Video[]>([])
const extractionConfirmOpen = ref(false)
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

async function samplingSubmitted(batch: { accepted: Array<{ video_id: string }> }) {
  ElMessage.success('采样方案已保存。')
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
    ElMessage.success(`已创建 ${batch.accepted.length} 个抽帧任务，拒绝 ${batch.rejected.length} 项。`)
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
onUnmounted(() => window.removeEventListener('vdm:tasks-settled', refreshAfterTask))
</script>

<template>
  <main class="workbench-shell">
    <section class="workspace">
        <header class="workspace-toolbar">
          <div>
            <h1>视频资料库</h1>
            <span>{{ total }} 个视频</span>
          </div>
          <el-button
            v-if="canEdit"
            data-test="import-videos"
            type="primary"
            :disabled="importLimitReached"
            :title="importLimitReached ? '项目视频数量已达上限（999）' : '导入视频'"
            @click="importOpen = true"
          >
            导入视频
          </el-button>
        </header>

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
            <el-button data-test="batch-configure" @click="configure(selected)">批量配置采样</el-button>
            <el-button data-test="batch-extract" @click="extract(selected)">批量抽帧</el-button>
            </div>
          </template>
          <template v-else>
            <span>共 {{ total }} 个视频</span>
            <span>当前页 {{ enabledOnPage }} 个已启用</span>
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
              <span>启用帧/采样帧</span>
              <span>媒体状态</span>
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
              <span class="status-mark" :data-status="video.status">{{ statusLabels[video.status] }}</span>
              <div class="status-info" :title="videoWorkflowStatus(video).detail">
                <span
                  class="workflow-state"
                  :data-state="videoWorkflowStatus(video).code"
                >{{ videoWorkflowStatus(video).primary }}</span>
                <span
                  v-for="flag in videoWorkflowStatus(video).flags"
                  :key="flag"
                  class="workflow-flag"
                  :data-flag="flag"
                >{{ flag }}</span>
                <small v-if="videoWorkflowStatus(video).detail">
                  {{ videoWorkflowStatus(video).detail }}
                </small>
              </div>
              <div class="row-actions">
                <button
                  :data-test="`play-${video.id}`"
                  type="button"
                  :disabled="video.status !== 'ready'"
                  @click="playing = video"
                >播放</button>
                <button
                  v-if="canEdit"
                  :data-test="`configure-${video.id}`"
                  type="button"
                  :disabled="video.status !== 'ready'"
                  @click="configure([video.id])"
                >采样</button>
                <span v-else />
                <button
                  v-if="canEdit"
                  :data-test="`extract-${video.id}`"
                  type="button"
                  :disabled="!video.sampling"
                  @click="extract([video.id])"
                >抽帧</button>
                <span v-else />
                <button
                  :data-test="`annotate-${video.id}`"
                  type="button"
                  :disabled="!canEdit || !video.sampling?.extracted_frames"
                  @click="openAnnotation(video)"
                >标注</button>
                <button
                  :data-test="`frames-${video.id}`"
                  type="button"
                  :disabled="!video.sampling?.extracted_frames"
                  @click="frameVideo = video"
                >筛帧</button>
              </div>
            </article>
          </div>

          <div v-if="!loading && !videos.length" class="empty-state">
            <h2>项目中还没有视频</h2>
            <p>{{ canEdit ? '从本地目录或远程 URL 创建第一批导入任务。' : '项目编辑者导入视频后会显示在这里。' }}</p>
            <el-button v-if="canEdit" type="primary" @click="importOpen = true">导入视频</el-button>
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
    <SamplingDialog
      v-if="canEdit"
      v-model="samplingOpen"
      :project-id="projectId"
      :videos="samplingTargets"
      @submitted="samplingSubmitted"
    />
    <el-dialog
      append-to-body
      :model-value="configureChoiceTargets.length > 0"
      title="批量配置采样"
      width="min(540px, calc(100vw - 32px))"
      @update:model-value="!$event && (configureChoiceTargets = [])"
    >
      <p>选中的视频中已有 {{ configureChoiceTargets.filter((video) => video.sampling).length }} 个配置过采样方案。</p>
      <template #footer>
        <el-button @click="configureChoiceTargets = []">取消</el-button>
        <el-button
          data-test="configure-unconfigured"
          :disabled="!configureChoiceTargets.some((video) => !video.sampling)"
          @click="configureUnconfigured"
        >仅处理 {{ configureChoiceTargets.filter((video) => !video.sampling).length }} 个未配置视频</el-button>
        <el-button data-test="configure-all" type="warning" @click="configureAll">
          处理全部 {{ configureChoiceTargets.length }} 个视频
        </el-button>
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
        <el-button @click="extractionChoiceTargets = []">取消</el-button>
        <el-button
          data-test="extract-unextracted"
          :disabled="!extractionChoiceTargets.some((video) => !video.sampling?.extracted_frames)"
          @click="extractUnextracted"
        >仅处理 {{ extractionChoiceTargets.filter((video) => !video.sampling?.extracted_frames).length }} 个未抽帧视频</el-button>
        <el-button data-test="extract-all" type="danger" @click="extractAll">
          处理全部 {{ extractionChoiceTargets.length }} 个视频
        </el-button>
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
.workbench-shell {
  min-height: 100%;
  color: var(--vdw-ink);
  background: var(--vdw-canvas);
}

.workspace {
  min-width: 0;
  padding: 0 18px 26px;
}

.workspace-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 62px;
  border-bottom: 1px solid var(--vdw-rule);
}

.workspace-toolbar > div {
  display: flex;
  align-items: baseline;
  gap: 11px;
}

.workspace-toolbar h1 {
  margin: 0;
  font: 700 22px var(--vdw-title);
  letter-spacing: -0.02em;
}

.workspace-toolbar span {
  color: var(--vdw-muted);
  font: 13px var(--vdw-mono);
}

.workspace-toolbar :deep(.el-button) {
  height: var(--vdm-control-height);
  border-radius: 2px;
}

.video-action-lane {
  display: flex;
  align-items: center;
  gap: 13px;
  justify-content: flex-start;
  height: 48px;
  padding: 0 9px;
  color: var(--vdw-muted);
  font-size: 14px;
  border-bottom: 1px solid var(--vdw-rule);
}

.video-action-lane > div {
  display: flex;
  gap: 7px;
  margin-left: auto;
}

.video-action-lane :deep(.el-button) {
  height: var(--vdm-control-height);
  border-radius: 2px;
}

.selection-summary {
  display: flex;
  align-items: baseline;
  gap: 12px;
  color: var(--vdw-ink);
}

.selection-summary small {
  color: var(--vdw-muted);
  font-weight: 400;
}

.video-ledger {
  margin-top: 9px;
  background: white;
  border: 1px solid var(--vdw-rule);
}

.ledger-scroll {
  overflow-x: auto;
}

.ledger-row {
  display: grid;
  grid-template-columns: 33px 59px minmax(242px, 1.35fr) 79px 139px 108px 92px minmax(209px, 1fr) 306px;
  gap: 9px;
  align-items: center;
  min-width: 1292px;
  padding: 0 9px;
}

.ledger-head {
  height: 32px;
  color: var(--vdw-muted);
  font-size: 11px;
  background: #f5f7f9;
  border-bottom: 1px solid var(--vdw-rule);
}

.ledger-head > span:last-child {
  text-align: center;
}

.media-row {
  position: relative;
  min-height: var(--vdm-row-height);
  border-bottom: 1px solid #e7ebef;
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
  background: var(--vdw-teal);
}

.media-row[data-status='unavailable']::before {
  background: #c74c46;
}

.media-row[data-enabled='false'] {
  color: #65717c;
  background: #f6f8f9;
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
  --el-switch-on-color: var(--vdw-teal);
}

.readonly-enabled {
  color: var(--vdw-muted);
  font-size: 11px;
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
  font: 9px var(--vdw-mono);
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
  color: var(--vdw-muted);
  font-size: 13px;
}

.source-mark {
  width: fit-content;
  padding: 2px 4px;
  color: #315d78;
  font: 11px var(--vdw-mono);
  border: 1px solid #a8bfcd;
}

.media-spec {
  display: grid;
  gap: 2px;
  font-size: 12px;
}

.media-spec small {
  color: var(--vdw-muted);
  font-size: 11px;
}

.frame-count {
  font: 12px var(--vdw-mono);
}

.status-mark {
  width: fit-content;
  padding: 2px 5px;
  color: var(--vdw-muted);
  font-size: 11px;
  border: 1px solid #c8d0d7;
}

.status-mark[data-status='ready'] {
  color: #0d6b58;
  border-color: #70bda9;
}

.status-mark[data-status='unavailable'] {
  color: #a33e39;
  border-color: #d9aaa7;
}

.status-info {
  display: flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
  gap: 4px;
  color: #53616d;
  font-size: 11px;
  white-space: nowrap;
}

.workflow-state,
.workflow-flag {
  flex: none;
  padding: 2px 5px;
  border: 1px solid #b7c3cc;
}

.workflow-state[data-state^='running'],
.workflow-state[data-state^='queued'] {
  color: #0d6b58;
  border-color: #70bda9;
  background: #eef9f6;
}

.workflow-state[data-state='task-failed'],
.workflow-state[data-state='unavailable'],
.workflow-state[data-state='resampling-required'] {
  color: #a33e39;
  border-color: #d9aaa7;
  background: #fff3f2;
}

.workflow-flag[data-flag='视频停用'] {
  color: #a33e39;
}

.status-info small {
  overflow: hidden;
  color: var(--vdw-muted);
  text-overflow: ellipsis;
}

.row-actions {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  height: var(--vdm-control-height);
  border: 1px solid #cbd3da;
}

.row-actions > button,
.row-actions > span {
  min-width: 0;
  color: #284c5f;
  font: inherit;
  font-size: 13px;
  background: #fff;
  border: 0;
  border-right: 1px solid #d7dde2;
}

.row-actions > :last-child {
  border-right: 0;
}

.row-actions > button {
  cursor: pointer;
}

.row-actions > button:hover:not(:disabled) {
  color: white;
  background: var(--vdw-teal);
}

.row-actions > button:disabled,
.row-actions > span {
  color: #a6afb7;
  background: #f4f6f7;
  cursor: not-allowed;
}

.ledger-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 46px;
  padding: 4px 9px 4px 13px;
  border-top: 1px solid var(--vdw-rule);
}

.ledger-footer label {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--vdw-muted);
  font-size: 12px;
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
  font: 700 22px var(--vdw-title);
}

.empty-state p {
  margin: 0 0 16px;
  color: var(--vdw-muted);
  font-size: 13px;
}

video {
  display: block;
  width: 100%;
  max-height: 70vh;
  background: #0d171f;
}

@media (max-width: 760px) {
  .project-layout {
    display: block;
  }

  .project-rail {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .project-identity {
    border-bottom: 0;
  }

  .project-rail nav {
    display: flex;
    align-items: center;
    padding: 9px;
  }

  .project-rail nav a {
    padding: 9px 11px;
    border-bottom: 2px solid transparent;
    border-left: 0;
  }

  .project-rail nav a.active {
    border-bottom-color: var(--vdw-mint);
  }

  .project-capacity {
    grid-column: 1 / -1;
    margin-top: 0;
    padding: 8px 15px;
  }

  .workspace {
    padding: 0 9px 18px;
  }
}
</style>
