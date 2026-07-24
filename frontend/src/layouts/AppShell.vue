<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import { getCurrentUser, logout, type CurrentUser } from '../api/auth'
import { listProjects, type Project } from '../api/projects'
import {
  readRecentProjects,
  rememberProject,
  resolveProjectShortcuts,
} from '../navigation/recentProjects'

const route = useRoute()
const router = useRouter()
const user = ref<CurrentUser>()
const fallbackProjects = ref<Project[]>([])
const activeProject = ref<Project>()
const projectGroupOpen = ref(localStorage.getItem('vdm.nav-projects-open') !== 'false')
const savedCollapsed = localStorage.getItem('vdm.sidebar-collapsed')
const collapsed = ref(
  savedCollapsed === null
    ? window.innerWidth >= 768 && window.innerWidth < 1200
    : savedCollapsed === 'true',
)
const mobileOpen = ref(false)

const shortcuts = computed(() =>
  resolveProjectShortcuts(
    readRecentProjects(),
    fallbackProjects.value,
    activeProject.value,
  ),
)
const breadcrumbs = computed(() => {
  const items = [String(route.meta.section ?? '')]
  if (route.params.id && activeProject.value) items.push(activeProject.value.name)
  items.push(String(route.meta.page ?? ''))
  return items.filter(Boolean)
})

function toggleSidebar() {
  if (window.innerWidth < 768) {
    mobileOpen.value = !mobileOpen.value
    return
  }
  collapsed.value = !collapsed.value
  localStorage.setItem('vdm.sidebar-collapsed', String(collapsed.value))
}

function toggleProjectGroup() {
  projectGroupOpen.value = !projectGroupOpen.value
  localStorage.setItem('vdm.nav-projects-open', String(projectGroupOpen.value))
}

function projectLoaded(project: Project) {
  activeProject.value = project
  rememberProject(project)
}

async function signOut() {
  await logout()
  await router.replace('/login')
}

onMounted(async () => {
  const [currentUser, projects] = await Promise.all([getCurrentUser(), listProjects(1, 5)])
  user.value = currentUser
  fallbackProjects.value = projects.items
})
</script>

<template>
  <div
    class="app-shell"
    :class="{
      'app-shell--collapsed': collapsed,
      'app-shell--mobile-open': mobileOpen,
    }"
  >
    <button
      v-if="mobileOpen"
      class="app-sidebar-backdrop"
      type="button"
      aria-label="关闭导航"
      @click="mobileOpen = false"
    />
    <aside class="app-sidebar">
      <RouterLink class="app-brand" data-test="brand" to="/projects">VDM</RouterLink>
      <nav class="app-nav" aria-label="主导航">
        <div class="app-nav-group">
          <RouterLink data-test="nav-projects" title="数据集项目" to="/projects">
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 5h16v14H4zM8 9h8M8 13h8M8 17h5" /></svg>
            <span>数据集项目</span>
          </RouterLink>
          <button
            data-test="project-group-toggle"
            type="button"
            aria-label="展开或收起最近项目"
            @click="toggleProjectGroup"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m7 10 5 5 5-5" /></svg>
          </button>
        </div>
        <div v-if="projectGroupOpen && !collapsed" class="app-nav-children">
          <RouterLink
            v-for="project in shortcuts"
            :key="project.id"
            data-test="recent-project"
            :to="`/projects/${project.id}/videos`"
          >{{ project.name }}</RouterLink>
        </div>
      </nav>
      <footer class="app-sidebar-footer">
        <RouterLink
          v-if="user?.is_system_admin"
          data-test="nav-admin-users"
          title="用户管理"
          to="/admin/users"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM5 21a7 7 0 0 1 14 0" /></svg>
          <span>用户管理</span>
        </RouterLink>
        <div class="app-sidebar-user" :title="user?.username">
          <b>{{ user?.username.slice(0, 1).toUpperCase() }}</b>
          <span>{{ user?.username }}</span>
        </div>
      </footer>
    </aside>

    <section class="app-frame">
      <header class="app-topbar">
        <button data-test="sidebar-toggle" type="button" aria-label="展开或折叠侧栏" @click="toggleSidebar">
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
        <nav class="app-breadcrumb" aria-label="面包屑">
          <span v-for="item in breadcrumbs" :key="item">{{ item }}</span>
        </nav>
        <button class="task-center-trigger" data-test="task-center" type="button">任务中心</button>
        <details class="user-menu">
          <summary>{{ user?.username }}</summary>
          <RouterLink to="/account">账号设置</RouterLink>
          <RouterLink v-if="user?.is_system_admin" to="/admin/users">系统管理</RouterLink>
          <button type="button" @click="signOut">退出登录</button>
        </details>
      </header>
      <main class="app-content">
        <RouterView v-slot="{ Component }">
          <component :is="Component" @project-loaded="projectLoaded" />
        </RouterView>
      </main>
    </section>
  </div>
</template>
