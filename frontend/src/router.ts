import { createRouter, createWebHistory } from 'vue-router'

import { ApiError, getAuthStatus, getCurrentUser } from './api/auth'
import { getSetupStatus } from './api/setup'
import AppShell from './layouts/AppShell.vue'
import FocusLayout from './layouts/FocusLayout.vue'
import ProjectLayout from './layouts/ProjectLayout.vue'
import LoginView from './views/LoginView.vue'
import AccountView from './views/AccountView.vue'
import AnnotationWorkbenchView from './views/AnnotationWorkbenchView.vue'
import AdminUsersView from './views/AdminUsersView.vue'
import ProjectsView from './views/ProjectsView.vue'
import ProjectSettingsView from './views/ProjectSettingsView.vue'
import ProjectLabelsView from './views/ProjectLabelsView.vue'
import ProjectDatasetsView from './views/ProjectDatasetsView.vue'
import ProjectVideosView from './views/ProjectVideosView.vue'
import RegisterView from './views/RegisterView.vue'
import SetupView from './views/SetupView.vue'

export function createAppRouter() {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', redirect: '/projects' },
      { path: '/setup', component: SetupView },
      { path: '/login', component: LoginView },
      { path: '/register', component: RegisterView },
      { path: '/ready', redirect: '/projects' },
      {
        path: '/',
        component: AppShell,
        children: [
          {
            path: 'projects',
            name: 'projects',
            component: ProjectsView,
            meta: { section: '数据集项目', page: '全部项目' },
          },
          {
            path: 'projects/:id',
            component: ProjectLayout,
            children: [
              { path: '', redirect: { name: 'project-videos' } },
              {
                path: 'videos',
                name: 'project-videos',
                component: ProjectVideosView,
                meta: { section: '数据集项目', page: '原始数据' },
              },
              {
                path: 'labels',
                name: 'project-labels',
                component: ProjectLabelsView,
                meta: { section: '数据集项目', page: '标签管理' },
              },
              {
                path: 'datasets',
                name: 'project-datasets',
                component: ProjectDatasetsView,
                meta: { section: '数据集项目', page: '数据集管理' },
              },
              {
                path: 'settings',
                name: 'project-settings',
                component: ProjectSettingsView,
                meta: { section: '数据集项目', page: '项目设置' },
              },
            ],
          },
          {
            path: 'account',
            component: AccountView,
            meta: { section: '系统', page: '账号设置' },
          },
          {
            path: 'admin/users',
            component: AdminUsersView,
            meta: { section: '系统管理', page: '用户管理' },
          },
        ],
      },
      {
        path: '/projects/:id/videos/:videoId/annotation',
        component: FocusLayout,
        children: [
          {
            path: '',
            name: 'video-annotation',
            component: AnnotationWorkbenchView,
            meta: { section: '数据集项目', page: '在线标注' },
          },
        ],
      },
    ],
  })
  router.beforeEach(async (to) => {
    const { initialized } = await getSetupStatus()
    if (!initialized && to.path !== '/setup') return '/setup'
    if (!initialized) return

    const authStatus = await getAuthStatus()
    let user = null
    try {
      user = await getCurrentUser()
    } catch (reason) {
      if (!(reason instanceof ApiError) || reason.status !== 401) throw reason
    }

    if (!user) {
      if (to.path === '/login') return
      if (to.path === '/register' && authStatus.registration_enabled) return
      return '/login'
    }
    if (to.path === '/setup' || to.path === '/login' || to.path === '/register') return '/projects'
    if (to.path.startsWith('/admin/') && !user.is_system_admin) return '/projects'
  })
  return router
}
