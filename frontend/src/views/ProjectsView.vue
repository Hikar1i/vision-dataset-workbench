<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getCurrentUser, logout, type CurrentUser } from '../api/auth'
import { createProject, listProjects, type Project } from '../api/projects'

const router = useRouter()
const user = ref<CurrentUser | null>(null)
const projects = ref<Project[]>([])
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const loading = ref(false)
const showCreate = ref(false)
const name = ref('')
const description = ref('')
const creating = ref(false)
const error = ref('')
const valid = computed(() => name.value.trim().length > 0 && name.value.trim().length <= 128)

const roleLabels = { owner: '所有者', editor: '编辑者', viewer: '只读' } as const

async function load(nextPage = page.value) {
  loading.value = true
  error.value = ''
  try {
    const [currentUser, result] = await Promise.all([
      getCurrentUser(),
      listProjects(nextPage),
    ])
    user.value = currentUser
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
    await router.push(`/projects/${project.id}/settings`)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '项目创建失败'
  } finally {
    creating.value = false
  }
}

async function signOut() {
  try {
    await logout()
    await router.replace('/login')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '退出失败'
  }
}

onMounted(() => load())
</script>

<template>
  <main class="projects-shell">
    <header class="topbar">
      <router-link class="brand" to="/projects">VDW / PROJECTS</router-link>
      <nav v-if="user" aria-label="账号操作">
        <span>{{ user.username }}</span>
        <router-link data-test="account-link" to="/account">账号设置</router-link>
        <router-link v-if="user.is_system_admin" data-test="users-link" to="/admin/users">
          用户管理
        </router-link>
        <el-button data-test="logout" text @click="signOut">退出</el-button>
      </nav>
    </header>

    <section class="page-heading">
      <div>
        <span class="section-code">WORKSPACE / VIDEO PROJECTS</span>
        <h1>数据集项目</h1>
        <p>每个项目拥有独立成员和受管存储目录。</p>
      </div>
      <el-button data-test="show-create" type="primary" @click="showCreate = !showCreate">
        {{ showCreate ? '取消新建' : '新建项目' }}
      </el-button>
    </section>

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
        <router-link
          :data-test="`open-${project.id}`"
          :to="`/projects/${project.id}/settings`"
        >
          打开
        </router-link>
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
  </main>
</template>

<style scoped>
.projects-shell {
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
.project-identity code {
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
  gap: 18px;
  font-size: 14px;
}

nav > span {
  color: #8795a3;
}

nav a,
.project-row > a {
  color: #76a7ff;
  text-decoration: none;
}

.page-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding: 48px 0 28px;
  border-bottom: 1px solid #d8dee6;
}

.section-code {
  color: #2563eb;
}

h1 {
  margin: 12px 0 6px;
  font-family: Bahnschrift, "Arial Narrow", "Noto Sans SC", sans-serif;
  font-size: 36px;
  letter-spacing: -0.04em;
}

.page-heading p,
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
  gap: 40px;
  padding: 28px;
}

.create-panel header {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.create-panel form > .el-button {
  width: 100%;
}

.index-row {
  display: grid;
  grid-template-columns: minmax(280px, 2fr) 100px 140px 130px 60px;
  gap: 20px;
  align-items: center;
  min-width: 780px;
}

.index-header {
  padding: 12px 20px;
  color: #687482;
  font-size: 12px;
  background: #f8fafc;
  border-bottom: 1px solid #d8dee6;
}

.project-row {
  padding: 18px 20px;
  border-bottom: 1px solid #e6eaf0;
}

.project-row:last-of-type {
  border-bottom: 0;
}

.project-identity {
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr);
  gap: 16px;
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
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-mark {
  width: fit-content;
  padding: 4px 7px;
  color: #3f4c59;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
  border: 1px solid #cbd3dd;
}

.role-mark[data-role='owner'] {
  color: #0f6c59;
  border-color: #78cdb6;
}

.project-row time,
.project-row > span {
  color: #687482;
  font-size: 13px;
}

.empty-state {
  padding: 72px 32px;
  text-align: center;
}

.empty-state h2 {
  margin: 16px 0 8px;
  font-size: 28px;
}

.empty-state .el-button {
  margin-top: 24px;
}

.el-pagination {
  justify-content: flex-end;
  padding: 20px;
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
