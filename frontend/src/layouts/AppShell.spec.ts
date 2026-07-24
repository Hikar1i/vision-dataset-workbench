import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AppShell from './AppShell.vue'

vi.mock('../api/auth', () => ({
  getCurrentUser: vi.fn().mockResolvedValue({
    id: 'admin-id',
    username: 'admin',
    status: 'active',
    is_system_admin: true,
  }),
  logout: vi.fn(),
}))
vi.mock('../api/projects', () => ({
  listProjects: vi.fn().mockResolvedValue({
    items: Array.from({ length: 6 }, (_, index) => ({
      id: `project-${index}`,
      name: `Project ${index}`,
    })),
    total: 6,
    page: 1,
    page_size: 5,
  }),
}))

async function mountShell() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/',
        component: AppShell,
        children: [
          {
            path: 'projects',
            component: { template: '<div>projects</div>' },
            meta: { section: '数据集项目', page: '全部项目' },
          },
          { path: 'projects/:id/videos', component: { template: '<div />' } },
          { path: 'account', component: { template: '<div />' } },
          { path: 'admin/users', component: { template: '<div />' } },
        ],
      },
    ],
  })
  await router.push('/projects')
  await router.isReady()
  const wrapper = mount({ template: '<RouterView />' }, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('AppShell', () => {
  beforeEach(() => {
    localStorage.clear()
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
  })

  it('shows implemented navigation and at most five project shortcuts', async () => {
    const wrapper = await mountShell()

    expect(wrapper.get('[data-test="brand"]').text()).toBe('VDM')
    expect(wrapper.get('[data-test="nav-projects"]').text()).toContain('数据集项目')
    expect(wrapper.findAll('[data-test="recent-project"]')).toHaveLength(5)
    expect(wrapper.text()).not.toContain('超参模板')
    expect(wrapper.find('[data-test="nav-admin-users"]').exists()).toBe(true)
  })

  it('persists sidebar and project group preferences', async () => {
    const wrapper = await mountShell()

    await wrapper.get('[data-test="sidebar-toggle"]').trigger('click')
    await wrapper.get('[data-test="project-group-toggle"]').trigger('click')

    expect(localStorage.getItem('vdm.sidebar-collapsed')).toBe('true')
    expect(localStorage.getItem('vdm.nav-projects-open')).toBe('false')
  })
})
