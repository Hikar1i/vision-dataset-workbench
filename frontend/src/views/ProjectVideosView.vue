<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  createExtractions,
  listVideos,
  videoContentUrl,
  videoThumbnailUrl,
  type ImportBatch,
  type Video,
} from '../api/media'
import { getProject, type Project } from '../api/projects'
import ImportVideosDialog from '../components/ImportVideosDialog.vue'
import FramesDialog from '../components/FramesDialog.vue'
import ProjectTaskDrawer from '../components/ProjectTaskDrawer.vue'
import SamplingDialog from '../components/SamplingDialog.vue'

const route = useRoute()
const projectId = String(route.params.id)
const project = ref<Project | null>(null)
const videos = ref<Video[]>([])
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const loading = ref(false)
const importOpen = ref(false)
const taskOpen = ref(false)
const playing = ref<Video | null>(null)
const frameVideo = ref<Video | null>(null)
const selected = ref<string[]>([])
const samplingOpen = ref(false)
const samplingVideoIds = ref<string[]>([])
const error = ref('')
const notice = ref('')

const canEdit = computed(() => project.value?.role === 'owner' || project.value?.role === 'editor')
const roleLabels = { owner: '所有者', editor: '编辑者', viewer: '只读' } as const
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

async function load(nextPage = page.value) {
  loading.value = true
  error.value = ''
  try {
    const [projectResult, videoResult] = await Promise.all([
      getProject(projectId),
      listVideos(projectId, nextPage),
    ])
    project.value = projectResult
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

function imported(batch: ImportBatch) {
  notice.value = `已创建 ${batch.accepted.length} 个任务，跳过 ${batch.skipped.length} 项，拒绝 ${batch.rejected.length} 项。`
  taskOpen.value = true
  void load(1)
}

function configure(videoIds: string[]) {
  samplingVideoIds.value = videoIds
  samplingOpen.value = true
}

function samplingSubmitted() {
  notice.value = '采样方案已保存。'
  selected.value = []
  void load()
}

async function extract(videoIds: string[]) {
  error.value = ''
  try {
    const batch = await createExtractions(projectId, videoIds)
    notice.value = `已创建 ${batch.accepted.length} 个抽帧任务，拒绝 ${batch.rejected.length} 项。`
    selected.value = []
    taskOpen.value = true
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '抽帧任务创建失败'
  }
}

onMounted(() => load())
</script>

<template>
  <main class="video-shell">
    <header class="topbar">
      <router-link class="brand" to="/projects">VDW / MEDIA DESK</router-link>
      <nav v-if="project" aria-label="项目导航">
        <router-link class="active" :to="`/projects/${projectId}/videos`">视频</router-link>
        <router-link data-test="settings-link" :to="`/projects/${projectId}/settings`">设置</router-link>
        <el-button text data-test="task-drawer" @click="taskOpen = true">任务</el-button>
      </nav>
    </header>

    <section v-if="project" class="project-strip">
      <div>
        <code>PROJECT / {{ project.id.slice(0, 8) }}</code>
        <strong>{{ project.name }}</strong>
        <span>{{ project.description || '暂无项目描述' }}</span>
      </div>
      <span class="role-mark" :data-role="project.role">{{ roleLabels[project.role] }}</span>
    </section>

    <section class="page-heading">
      <div>
        <span class="section-code">VIDEO INDEX / {{ total }}</span>
        <h1>视频资料库</h1>
        <p>受管原始视频、导入状态与媒体元数据。</p>
      </div>
      <el-button
        v-if="canEdit"
        data-test="import-videos"
        type="primary"
        @click="importOpen = true"
      >
        导入视频
      </el-button>
    </section>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert v-if="notice" :title="notice" type="success" :closable="false" />

    <section v-if="canEdit && selected.length" class="batch-bar">
      <strong>已选择 {{ selected.length }} 个视频</strong>
      <div>
        <el-button data-test="batch-configure" @click="configure(selected)">批量配置采样</el-button>
        <el-button data-test="batch-extract" type="primary" @click="extract(selected)">批量抽帧</el-button>
      </div>
    </section>

    <section v-loading="loading" class="video-index">
      <header v-if="videos.length" class="video-row table-head" :class="{ selectable: canEdit }">
        <span v-if="canEdit"></span><span>媒体</span><span>来源</span><span>规格 / 采样</span><span>状态</span><span>操作</span>
      </header>
      <article
        v-for="video in videos"
        :key="video.id"
        class="video-row media-row"
        :class="{ selectable: canEdit }"
        :data-status="video.status"
      >
        <input
          v-if="canEdit"
          v-model="selected"
          :data-test="`select-${video.id}`"
          type="checkbox"
          :value="video.id"
          :disabled="video.status !== 'ready'"
          aria-label="选择视频"
        />
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
            <strong>{{ video.title }}</strong>
            <p>{{ video.source_name || video.source_url || '等待 Worker 解析来源' }}</p>
          </div>
        </div>
        <span class="source-mark">{{ video.source_type === 'local' ? 'LOCAL' : 'REMOTE' }}</span>
        <div class="media-spec">
          <span>{{ video.width && video.height ? `${video.width}×${video.height}` : '—' }}</span>
          <small>{{ duration(video.duration) }} · {{ fileSize(video.file_size) }}</small>
          <small v-if="video.sampling">
            {{ video.sampling.state === 'sampled' ? '已采样' : '待抽帧' }} ·
            {{ video.sampling.enabled_frames }}/{{ video.sampling.extracted_frames || video.sampling.expected_frames }} 帧
          </small>
        </div>
        <span class="status-mark" :data-status="video.status">{{ statusLabels[video.status] }}</span>
        <div class="actions">
          <el-button
            v-if="video.status === 'ready'"
            :data-test="`play-${video.id}`"
            text
            @click="playing = video"
          >
            播放
          </el-button>
          <el-button
            v-if="canEdit && video.status === 'ready'"
            :data-test="`configure-${video.id}`"
            text
            @click="configure([video.id])"
          >采样</el-button>
          <el-button
            v-if="canEdit && video.sampling"
            :data-test="`extract-${video.id}`"
            text
            @click="extract([video.id])"
          >抽帧</el-button>
          <el-button
            v-if="video.sampling?.extracted_frames"
            :data-test="`frames-${video.id}`"
            text
            @click="frameVideo = video"
          >帧</el-button>
        </div>
      </article>

      <div v-if="!loading && !videos.length" class="empty-state">
        <span class="section-code">MEDIA INDEX / EMPTY</span>
        <h2>项目中还没有视频</h2>
        <p>{{ canEdit ? '从本地目录或远程 URL 创建第一批导入任务。' : '项目编辑者导入视频后会显示在这里。' }}</p>
        <el-button v-if="canEdit" type="primary" @click="importOpen = true">导入视频</el-button>
      </div>

      <el-pagination
        v-if="total > pageSize"
        layout="prev, pager, next"
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        @current-change="load"
      />
    </section>

    <el-dialog
      :model-value="playing !== null"
      :title="playing?.title"
      width="min(960px, calc(100vw - 32px))"
      :teleported="false"
      @update:model-value="!$event && (playing = null)"
    >
      <video
        v-if="playing"
        controls
        preload="metadata"
        :src="videoContentUrl(projectId, playing.id)"
      />
    </el-dialog>

    <ImportVideosDialog
      v-if="canEdit"
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
    <ProjectTaskDrawer
      v-model="taskOpen"
      :project-id="projectId"
      :can-manage="canEdit"
      @settled="load()"
    />
  </main>
</template>

<style scoped>
.video-shell {
  min-height: 100vh;
  padding: 0 clamp(20px, 4vw, 56px) 64px;
  color: #17212b;
  background: #f4f7fa;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 64px;
  margin: 0 calc(clamp(20px, 4vw, 56px) * -1);
  padding: 0 clamp(20px, 4vw, 56px);
  color: #dce5ed;
  background: #17212b;
  border-bottom: 2px solid #76dfc2;
}

.brand,
.section-code,
.project-strip code,
.thumbnail code,
.source-mark {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
  letter-spacing: 0.1em;
}

.brand {
  color: #76dfc2;
  text-decoration: none;
}

nav {
  display: flex;
  align-items: center;
  gap: 20px;
}

nav a {
  color: #9aa7b4;
  font-size: 13px;
  text-decoration: none;
}

nav a.active {
  color: #f7fafc;
}

.project-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  min-height: 54px;
  margin: 0 calc(clamp(20px, 4vw, 56px) * -1);
  padding: 0 clamp(20px, 4vw, 56px);
  background: #e9eef3;
  border-bottom: 1px solid #d0d8e1;
}

.project-strip > div {
  display: flex;
  gap: 16px;
  align-items: baseline;
  min-width: 0;
}

.project-strip code {
  color: #2563eb;
}

.project-strip span:not(.role-mark) {
  overflow: hidden;
  color: #687482;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding: 42px 0 26px;
  border-bottom: 1px solid #d8dee6;
}

.section-code {
  color: #2563eb;
}

h1 {
  margin: 10px 0 5px;
  font-family: Bahnschrift, "Arial Narrow", "Noto Sans SC", sans-serif;
  font-size: 34px;
  letter-spacing: -0.04em;
}

.page-heading p,
.media-identity p,
.empty-state p {
  margin: 0;
  color: #687482;
}

.video-index {
  margin-top: 22px;
  overflow-x: auto;
  background: white;
  border: 1px solid #d8dee6;
}

.batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 18px;
  padding: 10px 14px;
  background: #e8f5f1;
  border: 1px solid #9bd4c5;
}

.video-row {
  display: grid;
  grid-template-columns: minmax(360px, 2fr) 90px 180px 100px 220px;
  gap: 18px;
  align-items: center;
  min-width: 880px;
}

.video-row.selectable {
  grid-template-columns: 24px minmax(360px, 2fr) 90px 180px 100px 220px;
}

.table-head {
  padding: 11px 16px;
  color: #687482;
  font-size: 12px;
  background: #f8fafc;
  border-bottom: 1px solid #d8dee6;
}

.media-row {
  position: relative;
  min-height: 84px;
  padding: 12px 16px 12px 20px;
  border-bottom: 1px solid #e6eaf0;
}

.media-row::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: #9aa7b4;
  content: '';
}

.media-row[data-status='ready']::before {
  background: #39b79a;
}

.media-row[data-status='unavailable']::before {
  background: #d5574f;
}

.media-identity {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
}

.thumbnail {
  position: relative;
  height: 58px;
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
  right: 5px;
  bottom: 4px;
  padding: 2px 4px;
  color: #c9fff0;
  background: rgb(13 23 32 / 76%);
}

.media-identity strong {
  display: block;
  margin-bottom: 5px;
}

.media-identity p {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-mark {
  width: fit-content;
  padding: 4px 6px;
  color: #325d9d;
  border: 1px solid #9eb9df;
}

.media-spec {
  display: grid;
  gap: 4px;
  font-size: 13px;
}

.media-spec small {
  color: #687482;
}

.status-mark,
.role-mark {
  width: fit-content;
  padding: 4px 7px;
  color: #687482;
  font-size: 11px;
  border: 1px solid #cbd3dd;
}

.status-mark[data-status='ready'],
.role-mark[data-role='owner'] {
  color: #0f6c59;
  border-color: #78cdb6;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.actions a {
  color: #2563eb;
  font-size: 13px;
  text-decoration: none;
}

.empty-state {
  padding: 72px 30px;
  text-align: center;
}

.empty-state h2 {
  margin: 14px 0 8px;
  font-size: 26px;
}

.empty-state .el-button {
  margin-top: 22px;
}

video {
  display: block;
  width: 100%;
  max-height: 70vh;
  background: #0d171f;
}

@media (max-width: 700px) {
  .topbar,
  .page-heading,
  .project-strip,
  .project-strip > div {
    align-items: flex-start;
    flex-direction: column;
  }

  .topbar,
  .project-strip {
    padding-top: 16px;
    padding-bottom: 16px;
  }

  nav {
    flex-wrap: wrap;
  }
}
</style>
