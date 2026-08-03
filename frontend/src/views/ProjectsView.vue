<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'

import { ApiError } from '../api/auth'
import { createProject, deleteProject, listProjects, type Project } from '../api/projects'

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
    <header class="content-toolbar">
      <div class="content-toolbar-title">
        <h1 data-test="page-title">数据集项目</h1>
        <span>{{ total }} 个项目</span>
      </div>
      <el-button data-test="show-create" type="primary" @click="showCreate = !showCreate">
        {{ showCreate ? '取消新建' : '新建项目' }}
      </el-button>
    </header>

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
  color: #17212b;
  background: #f4f7fa;
}
.section-code,
.project-identity code {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  letter-spacing: 0.1em;
}

.project-actions a {
  color: #76a7ff;
  text-decoration: none;
}

.project-actions {
  display: flex;
  gap: 14px;
  align-items: center;
}

.section-code {
  color: #2563eb;
}

.project-row p,
.empty-state p {
  margin: 0;
  color: #687482;
}

.create-panel,
.project-index {
  margin-top: 24px;
  background: white;
  border: 1px solid #d8dee6;
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
  color: #687482;
  font-size: 13px;
  background: #f8fafc;
  border-bottom: 1px solid #d8dee6;
}

.project-row {
  padding: 20px 22px;
  border-bottom: 1px solid #e6eaf0;
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
  color: #16866f;
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
  color: #3f4c59;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  border: 1px solid #cbd3dd;
}

.role-mark[data-role='owner'] {
  color: #0f6c59;
  border-color: #78cdb6;
}

.project-row time,
.project-row > span {
  color: #687482;
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
  border-top: 1px solid #d8dee6;
}

@media (max-width: 760px) {
  .topbar,
  .page-heading,
  nav {
    align-items: flex-start;
  }

  .topbar,
  .page-heading {
    flex-direction: column;
  }

  .topbar {
    padding-top: 18px;
    padding-bottom: 18px;
  }

  nav {
    flex-wrap: wrap;
  }

  .create-panel {
    grid-template-columns: 1fr;
  }

  .project-index {
    overflow-x: auto;
  }
}
</style>
