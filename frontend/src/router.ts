import { createRouter, createWebHistory } from 'vue-router'

import { ApiError, getAuthStatus, getCurrentUser } from './api/auth'
import { getSetupStatus } from './api/setup'
import LoginView from './views/LoginView.vue'
import AccountView from './views/AccountView.vue'
import AdminUsersView from './views/AdminUsersView.vue'
import ProjectsView from './views/ProjectsView.vue'
import ProjectSettingsView from './views/ProjectSettingsView.vue'
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
      { path: '/account', component: AccountView },
      { path: '/admin/users', component: AdminUsersView },
      { path: '/ready', redirect: '/projects' },
      { path: '/projects', component: ProjectsView },
      { path: '/projects/:id/settings', component: ProjectSettingsView },
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
