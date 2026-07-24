<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, onUnmounted, ref } from 'vue'

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
import FramesDialog from '../components/FramesDialog.vue'
import ImportVideosDialog from '../components/ImportVideosDialog.vue'
import SamplingDialog from '../components/SamplingDialog.vue'
import { videoStatusInfo } from './videoStatus'

const props = defineProps<{ project: Project }>()
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
const samplingVideoIds = ref<string[]>([])
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

async function load(nextPage = page.value, nextPageSize = pageSize.value) {
  loading.value = true
  error.value = ''
  try {
    const videoResult = await listVideos(projectId, nextPage, nextPageSize)
    videos.value = videoResult.items
    selected.value = []
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

function configure(videoIds: string[]) {
  samplingVideoIds.value = videoIds
  samplingOpen.value = true
}

function samplingSubmitted() {
  ElMessage.success('采样方案已保存。')
  selected.value = []
  void load()
}

async function extract(videoIds: string[]) {
  error.value = ''
  try {
    const batch = await createExtractions(projectId, videoIds)
    ElMessage.success(`已创建 ${batch.accepted.length} 个抽帧任务，拒绝 ${batch.rejected.length} 项。`)
    selected.value = []
    await load()
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
            <strong>已选择 {{ selected.length }} 个视频</strong>
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
              <span>状态信息</span>
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
                  <code>{{ video.id.slice(0, 8) }}</code>
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
              <span class="status-info" :title="videoStatusInfo(video)">{{ videoStatusInfo(video) }}</span>
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
                  :data-test="`frames-${video.id}`"
                  type="button"
                  :disabled="!video.sampling?.extracted_frames"
                  @click="frameVideo = video"
                >帧</button>
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
      :model-value="playing !== null"
      :title="playing?.title"
      width="min(960px, calc(100vw - 32px))"
      :teleported="false"
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
      :video-ids="samplingVideoIds"
      @submitted="samplingSubmitted"
    />
    <FramesDialog
      :model-value="frameVideo !== null"
      :project-id="projectId"
      :video-id="frameVideo?.id || ''"
      :title="frameVideo?.title || ''"
      :can-edit="canEdit"
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
  padding: 0 16px 24px;
}

.workspace-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  border-bottom: 1px solid var(--vdw-rule);
}

.workspace-toolbar > div {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.workspace-toolbar h1 {
  margin: 0;
  font: 700 20px var(--vdw-title);
  letter-spacing: -0.02em;
}

.workspace-toolbar span {
  color: var(--vdw-muted);
  font: 12px var(--vdw-mono);
}

.workspace-toolbar :deep(.el-button) {
  height: var(--vdm-control-height);
  border-radius: 2px;
}

.video-action-lane {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: flex-start;
  height: 44px;
  padding: 0 8px;
  color: var(--vdw-muted);
  font-size: 13px;
  border-bottom: 1px solid var(--vdw-rule);
}

.video-action-lane > div {
  display: flex;
  gap: 6px;
  margin-left: auto;
}

.video-action-lane :deep(.el-button) {
  height: var(--vdm-control-height);
  border-radius: 2px;
}

.video-ledger {
  margin-top: 8px;
  background: white;
  border: 1px solid var(--vdw-rule);
}

.ledger-scroll {
  overflow-x: auto;
}

.ledger-row {
  display: grid;
  grid-template-columns: 30px 54px minmax(220px, 1.35fr) 72px 126px 98px 84px minmax(190px, 1fr) 224px;
  gap: 8px;
  align-items: center;
  min-width: 1120px;
  padding: 0 8px;
}

.ledger-head {
  height: 29px;
  color: var(--vdw-muted);
  font-size: 10px;
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
  height: 20px;
}

.enabled-cell :deep(.el-switch) {
  --el-switch-on-color: var(--vdw-teal);
}

.readonly-enabled {
  color: var(--vdw-muted);
  font-size: 10px;
}

.readonly-enabled[data-enabled='false'] {
  color: #a33e39;
}

.media-identity {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.thumbnail {
  position: relative;
  width: 72px;
  height: 42px;
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
  font: 7px var(--vdw-mono);
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
  font-size: 14px;
}

.media-identity p {
  margin: 0;
  color: var(--vdw-muted);
  font-size: 12px;
}

.source-mark {
  width: fit-content;
  padding: 2px 4px;
  color: #315d78;
  font: 9px var(--vdw-mono);
  border: 1px solid #a8bfcd;
}

.media-spec {
  display: grid;
  gap: 2px;
  font-size: 11px;
}

.media-spec small {
  color: var(--vdw-muted);
  font-size: 9px;
}

.frame-count {
  font: 11px var(--vdw-mono);
}

.status-mark {
  width: fit-content;
  padding: 2px 5px;
  color: var(--vdw-muted);
  font-size: 10px;
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
  overflow: hidden;
  color: #53616d;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-actions {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  height: var(--vdm-control-height);
  border: 1px solid #cbd3da;
}

.row-actions > button,
.row-actions > span {
  min-width: 0;
  color: #284c5f;
  font: inherit;
  font-size: 12px;
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
  min-height: 42px;
  padding: 4px 8px 4px 12px;
  border-top: 1px solid var(--vdw-rule);
}

.ledger-footer label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--vdw-muted);
  font-size: 11px;
}

.ledger-footer select {
  height: 26px;
  padding: 0 22px 0 7px;
  color: var(--vdw-ink);
  background: white;
  border: 1px solid #bfc8d0;
}

.empty-state {
  padding: 48px 24px;
  text-align: center;
}

.empty-state h2 {
  margin: 0 0 7px;
  font: 700 20px var(--vdw-title);
}

.empty-state p {
  margin: 0 0 16px;
  color: var(--vdw-muted);
  font-size: 12px;
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
    padding: 8px;
  }

  .project-rail nav a {
    padding: 8px 10px;
    border-bottom: 2px solid transparent;
    border-left: 0;
  }

  .project-rail nav a.active {
    border-bottom-color: var(--vdw-mint);
  }

  .project-capacity {
    grid-column: 1 / -1;
    margin-top: 0;
    padding: 7px 14px;
  }

  .workspace {
    padding: 0 8px 16px;
  }
}
</style>
