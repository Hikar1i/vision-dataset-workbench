import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { logout } from '../api/auth'
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
  const wrapper = mount(
    { template: '<RouterView />' },
    { global: { plugins: [router, ElementPlus] } },
  )
  await flushPromises()
  return { router, wrapper }
}

describe('AppShell', () => {
  beforeEach(() => {
    vi.mocked(logout).mockClear()
    localStorage.clear()
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
  })

  it('shows implemented navigation and at most five project shortcuts', async () => {
    const { wrapper } = await mountShell()

    expect(wrapper.get('[data-test="brand"]').text()).toBe('VDM')
    expect(wrapper.get('[data-test="nav-projects"]').text()).toContain('数据集项目')
    expect(wrapper.findAll('[data-test="recent-project"]')).toHaveLength(5)
    expect(wrapper.text()).not.toContain('超参模板')
    expect(wrapper.find('[data-test="nav-admin-users"]').exists()).toBe(true)
  })

  it('persists sidebar and project group preferences', async () => {
    const { wrapper } = await mountShell()

    await wrapper.get('[data-test="sidebar-toggle"]').trigger('click')
    await wrapper.get('[data-test="project-group-toggle"]').trigger('click')

    expect(localStorage.getItem('vdm.sidebar-collapsed')).toBe('true')
    expect(localStorage.getItem('vdm.nav-projects-open')).toBe('false')
  })

  it('uses fixed icon slots while the sidebar changes width', async () => {
    const { wrapper } = await mountShell()

    expect(wrapper.get('[data-test="brand"] .app-sidebar-icon').text()).toBe('VDM')
    expect(wrapper.find('[data-test="nav-projects"] .app-sidebar-icon svg').exists()).toBe(true)
    expect(wrapper.find('[data-test="nav-admin-users"] .app-sidebar-icon svg').exists()).toBe(true)

    await wrapper.get('[data-test="sidebar-toggle"]').trigger('click')

    expect(wrapper.get('.app-shell').classes()).toContain('app-shell--collapsed')
    expect(wrapper.get('[data-test="brand"] .app-sidebar-icon').text()).toBe('VDM')
  })

  it('routes and signs out through the overlay user menu commands', async () => {
    const { router, wrapper } = await mountShell()
    const dropdown = wrapper.getComponent({ name: 'ElDropdown' })

    expect(wrapper.find('details.user-menu').exists()).toBe(false)
    dropdown.vm.$emit('command', 'account')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/account')

    dropdown.vm.$emit('command', 'logout')
    await flushPromises()
    expect(logout).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.path).toBe('/login')
  })
})
