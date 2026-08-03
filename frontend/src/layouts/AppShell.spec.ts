import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElNotification } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { logout } from '../api/auth'
import { getCapabilities } from '../api/capabilities'
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
vi.mock('../api/capabilities', () => ({
  getCapabilities: vi.fn(),
}))

const readyCapabilities = {
  gpu: { available: true, reason: null, devices: [] },
  pytorch_cuda: { available: true, reason: null },
  onnx_cuda: { available: true, reason: null },
  features: {
    manual_annotation: { available: true, reason: null },
    yolo_auto_annotation: { available: true, reason: null },
    grounding_dino_auto_annotation: { available: true, reason: null },
    model_training: { available: true, reason: null },
  },
}

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
            component: {
              emits: ['project-deleted'],
              template: '<button data-test="emit-project-deleted" @click="$emit(\'project-deleted\', \'project-1\')">projects</button>',
            },
            meta: { section: '数据集项目', page: '全部项目' },
          },
          {
            path: 'projects/:id/videos',
            component: {
              emits: ['project-loaded'],
              mounted() {
                this.$emit('project-loaded', { id: 'project-1', name: 'Project 1' })
              },
              template: '<div />',
            },
          },
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
    sessionStorage.clear()
    vi.mocked(getCapabilities).mockResolvedValue(readyCapabilities)
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

  it('keeps project order stable until the app shell is mounted again', async () => {
    localStorage.setItem('vdm.recent-projects', JSON.stringify([
      { id: 'project-0', name: 'Project 0', visitedAt: 30 },
      { id: 'project-1', name: 'Project 1', visitedAt: 20 },
      { id: 'project-2', name: 'Project 2', visitedAt: 10 },
    ]))
    const first = await mountShell()
    expect(first.wrapper.findAll('[data-test="recent-project"]').slice(0, 3).map(
      (item) => item.text(),
    )).toEqual(['Project 0', 'Project 1', 'Project 2'])

    await first.router.push('/projects/project-1/videos')
    await flushPromises()

    expect(first.wrapper.findAll('[data-test="recent-project"]').slice(0, 3).map(
      (item) => item.text(),
    )).toEqual(['Project 0', 'Project 1', 'Project 2'])
    expect(JSON.parse(localStorage.getItem('vdm.recent-projects') ?? '[]')[0].id).toBe(
      'project-1',
    )
    first.wrapper.unmount()

    const second = await mountShell()
    expect(second.wrapper.findAll('[data-test="recent-project"]').slice(0, 3).map(
      (item) => item.text(),
    )).toEqual(['Project 1', 'Project 0', 'Project 2'])
    second.wrapper.unmount()
  })

  it('persists sidebar and project group preferences', async () => {
    const { wrapper } = await mountShell()

    const sidebarToggle = wrapper.get('[data-test="sidebar-toggle"]')
    expect(sidebarToggle.attributes('aria-label')).toBe('收起侧栏')
    expect(sidebarToggle.find('.anticon-menu-fold').exists()).toBe(true)
    await sidebarToggle.trigger('click')
    expect(sidebarToggle.attributes('aria-label')).toBe('展开侧栏')
    expect(sidebarToggle.find('.anticon-menu-unfold').exists()).toBe(true)
    await wrapper.get('[data-test="project-group-toggle"]').trigger('click')

    expect(localStorage.getItem('vdm.sidebar-collapsed')).toBe('true')
    expect(localStorage.getItem('vdm.nav-projects-open')).toBe('false')
  })

  it('removes a deleted project from the current sidebar and storage', async () => {
    localStorage.setItem('vdm.recent-projects', JSON.stringify([
      { id: 'project-1', name: 'Project 1', visitedAt: 20 },
      { id: 'project-2', name: 'Project 2', visitedAt: 10 },
    ]))
    const { wrapper } = await mountShell()

    await wrapper.get('[data-test="emit-project-deleted"]').trigger('click')

    expect(wrapper.findAll('[data-test="recent-project"]').map((item) => item.text()))
      .not.toContain('Project 1')
    expect(JSON.parse(localStorage.getItem('vdm.recent-projects') ?? '[]'))
      .toHaveLength(1)
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

  it('shows an unavailable GPU warning only once per browser session', async () => {
    vi.mocked(getCapabilities).mockResolvedValue({
      ...readyCapabilities,
      gpu: {
        available: false,
        reason: '未检测到可用 NVIDIA GPU',
        devices: [],
      },
    })
    const warning = vi.spyOn(ElNotification, 'warning')

    const first = await mountShell()
    expect(warning).toHaveBeenCalledOnce()
    expect(warning).toHaveBeenCalledWith(
      expect.objectContaining({
        title: '部分 GPU 功能未启用',
        message: '未检测到可用 NVIDIA GPU',
      }),
    )
    first.wrapper.unmount()

    const second = await mountShell()
    expect(warning).toHaveBeenCalledOnce()
    second.wrapper.unmount()
  })
})
