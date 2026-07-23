import { createRouter, createWebHistory } from 'vue-router'

import { getSetupStatus } from './api/setup'
import ReadyView from './views/ReadyView.vue'
import SetupView from './views/SetupView.vue'

export function createAppRouter() {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', redirect: '/ready' },
      { path: '/setup', component: SetupView },
      { path: '/ready', component: ReadyView },
    ],
  })
  router.beforeEach(async (to) => {
    const { initialized } = await getSetupStatus()
    if (!initialized && to.path !== '/setup') return '/setup'
    if (initialized && to.path === '/setup') return '/ready'
  })
  return router
}
