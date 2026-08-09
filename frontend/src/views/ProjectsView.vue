<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'

import { ApiError } from '../api/auth'
import { createProject, deleteProject, listProjects, type Project } from '../api/projects'
import PageHeader from '../components/PageHeader.vue'

const emit = defineEmits<{ 'project-deleted': [id: string] }>()
const router = useRouter()
const projects = ref<Project[]>([])
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const loading = ref(false)
const showCreate = ref(false)
const name = ref('')
const description = ref('')
const creating = ref(false)
const deleting = ref('')
const error = ref('')
const valid = computed(() => name.value.trim().length > 0 && name.value.trim().length <= 128)

const roleLabels = { owner: '所有者', editor: '编辑者', viewer: '只读' } as const

async function load(nextPage = page.value) {
  loading.value = true
  error.value = ''
  try {
    const result = await listProjects(nextPage)
    projects.value = result.items
    page.value = result.page
    pageSize.value = result.page_size
    total.value = result.total
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '项目列表加载失败'
  } finally {
    loading.value = false
  }
}

async function create() {
  if (!valid.value) return
  creating.value = true
  error.value = ''
  try {
    const project = await createProject(name.value, description.value)
    await router.push(`/projects/${project.id}/videos`)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '项目创建失败'
  } finally {
    creating.value = false
  }
}

async function remove(project: Project) {
  try {
    await ElMessageBox.confirm(
      `删除数据集项目“${project.name}”？项目目录和完整元数据将移入工作区 .deleted 目录，项目随后不再显示。`,
      '删除数据集项目',
      {
        type: 'warning',
        confirmButtonText: '删除项目',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return
  }
  deleting.value = project.id
  try {
    await deleteProject(project.id)
    emit('project-deleted', project.id)
    ElMessage.success('项目已归档至逻辑删除目录。')
    await load(page.value > 1 && projects.value.length === 1 ? page.value - 1 : page.value)
  } catch (reason) {
    ElMessage.error(
      reason instanceof ApiError && reason.status === 409
        ? '项目仍有排队中或运行中任务，请先处理任务。'
        : reason instanceof Error ? reason.message : '项目删除失败',
    )
  } finally {
    deleting.value = ''
  }
}

onMounted(() => load())
</script>

<template>
  <main class="content-page projects-shell">
    <PageHeader title="数据集项目">
      <template #meta><span data-test="page-stat">{{ total }} 个项目</span></template>
      <template #actions><el-button data-test="show-create" type="primary" @click="showCreate = !showCreate">{{ showCreate ? '取消新建' : '新建项目' }}</el-button></template>
    </PageHeader>

    <div class="content-body">

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <section v-if="showCreate" class="create-panel">
      <header>
        <span class="section-code">NEW / PROJECT</span>
        <strong>创建视频项目</strong>
      </header>
      <form @submit.prevent="create">
        <el-form label-position="top">
          <el-form-item label="项目名称">
            <el-input
              v-model="name"
              data-test="project-name"
              maxlength="128"
              show-word-limit
              autofocus
            />
          </el-form-item>
          <el-form-item label="描述">
            <el-input
              v-model="description"
              data-test="project-description"
              type="textarea"
              :rows="3"
              maxlength="2000"
              show-word-limit
            />
          </el-form-item>
        </el-form>
        <el-button native-type="submit" type="primary" :loading="creating" :disabled="!valid">
          创建并打开
        </el-button>
      </form>
    </section>

    <section v-loading="loading" class="project-index">
      <header v-if="projects.length" class="index-row index-header">
        <span>项目</span><span>权限</span><span>所有者</span><span>最近更新</span><span />
      </header>

      <article v-for="project in projects" :key="project.id" class="index-row project-row">
        <div class="project-identity">
          <code>{{ project.id.slice(0, 8) }}</code>
          <div>
            <strong>{{ project.name }}</strong>
            <p>{{ project.description || '暂无描述' }}</p>
          </div>
        </div>
        <span class="role-mark" :data-role="project.role">{{ roleLabels[project.role] }}</span>
        <span>{{ project.creator_username }}</span>
        <time :datetime="project.updated_at">{{ project.updated_at.slice(0, 10) }}</time>
        <div class="project-actions">
          <router-link
            :data-test="`open-${project.id}`"
            :to="`/projects/${project.id}/videos`"
          >打开</router-link>
          <el-button
            v-if="project.role === 'owner'"
            :data-test="`delete-${project.id}`"
            type="danger"
            link
            :loading="deleting === project.id"
            :disabled="Boolean(deleting)"
            @click="remove(project)"
          >删除</el-button>
        </div>
      </article>

      <div v-if="!loading && !projects.length" class="empty-state">
        <span class="section-code">PROJECT INDEX / EMPTY</span>
        <h2>还没有项目</h2>
        <p>创建第一个视频项目，随后可添加协作者和导入媒体。</p>
        <el-button type="primary" @click="showCreate = true">新建项目</el-button>
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
    </div>
  </main>
</template>

<style scoped>
.projects-shell {
  color: var(--vdw-ink);
  background: var(--vdw-canvas);
}
.section-code,
.project-identity code {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 14px;
  letter-spacing: 0.1em;
}

.project-actions a {
  padding: 7px 9px;
  color: var(--vdw-teal-hover);
  text-decoration: none;
  border: 1px solid transparent;
  border-radius: var(--vdm-radius-control);
  transition: color var(--vdm-motion-fast) ease, background-color var(--vdm-motion-fast) ease, border-color var(--vdm-motion-fast) ease, box-shadow var(--vdm-motion-fast) ease;
}

.project-actions a:hover {
  color: var(--vdw-ink);
  background: #edf7f4;
  border-color: #9fc9bf;
  box-shadow: 0 3px 9px rgb(24 43 55 / 10%);
}

.project-actions a:active {
  box-shadow: inset 0 2px 4px rgb(24 43 55 / 16%);
}

.project-actions {
  display: flex;
  gap: 14px;
  align-items: center;
}

.section-code {
  color: var(--vdw-teal);
}

.project-row p,
.empty-state p {
  margin: 0;
  color: var(--vdw-muted);
}

.create-panel,
.project-index {
  margin-top: 24px;
  background: var(--vdw-surface-raised);
  border: 1px solid var(--vdw-rule);
  border-radius: var(--vdm-radius-card);
}

.create-panel {
  display: grid;
  grid-template-columns: minmax(180px, 0.55fr) minmax(280px, 1fr);
  gap: 44px;
  padding: 31px;
}

.create-panel header {
  display: flex;
  flex-direction: column;
  gap: 13px;
}

.create-panel form > .el-button {
  width: 100%;
}

.index-row {
  display: grid;
  grid-template-columns: minmax(280px, 2fr) 100px 140px 130px 120px;
  gap: 22px;
  align-items: center;
  min-width: 858px;
}

.index-header {
  padding: 13px 22px;
  color: var(--vdw-muted);
  font-size: 14px;
  background: var(--vdw-surface);
  border-bottom: 1px solid var(--vdw-rule);
}

.project-row {
  padding: 20px 22px;
  border-bottom: 1px solid var(--vdw-rule);
}

.project-row:last-of-type {
  border-bottom: 0;
}

.project-identity {
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr);
  gap: 18px;
  align-items: center;
}

.project-identity code {
  color: var(--vdw-teal);
  font-size: 12px;
}

.project-identity strong {
  display: block;
  margin-bottom: 5px;
}

.project-identity p {
  overflow: hidden;
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-mark {
  width: fit-content;
  padding: 4px 8px;
  color: var(--vdw-muted);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 14px;
  border: 1px solid var(--vdw-rule);
}

.role-mark[data-role='owner'] {
  color: var(--vdw-teal-hover);
  border-color: var(--vdw-mint);
}

.project-row time,
.project-row > span {
  color: var(--vdw-muted);
  font-size: 14px;
}

.empty-state {
  padding: 79px 35px;
  text-align: center;
}

.empty-state h2 {
  margin: 16px 0 8px;
  font-size: 31px;
}

.empty-state .el-button {
  margin-top: 24px;
}

.el-pagination {
  justify-content: flex-end;
  padding: 22px;
  border-top: 1px solid var(--vdw-rule);
}
</style>
