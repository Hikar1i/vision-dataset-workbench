import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElNotification } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { logout } from '../api/auth'
import { getCapabilities } from '../api/capabilities'
import { rememberResource } from '../navigation/recentResources'
import { clearRecentRows, isRecentRow, markRecentRow } from '../ui/recentRows'
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
vi.mock('../api/models', () => ({
  listModelProjects: vi.fn().mockResolvedValue([
    { id: 'model-1', name: 'Model 1' },
    { id: 'model-2', name: 'Model 2' },
  ]),
}))
vi.mock('../api/training', () => ({
  listTrainingTasks: vi.fn().mockResolvedValue([
    { id: 'training-1', name: 'Training 1' },
    { id: 'training-2', name: 'Training 2' },
  ]),
}))

const readyCapabilities = {
  gpu: { available: true, reason: null, devices: [] },
  pytorch_cuda: { available: true, reason: null },
  features: {
    manual_annotation: { available: true, reason: null },
    yolo_auto_annotation: { available: true, reason: null },
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
            meta: { section: '数据集项目', page: '原始数据' },
          },
          {
            path: 'model-projects/:id',
            component: {
              mounted() {
                rememberResource('vdm.recent-model-projects', {
                  id: String(this.$route.params.id),
                  name: `Model ${String(this.$route.params.id).split('-')[1]}`,
                })
              },
              template: '<div />',
            },
          },
          {
            path: 'training-tasks/:id',
            component: {
              mounted() {
                rememberResource('vdm.recent-training-tasks', {
                  id: String(this.$route.params.id),
                  name: `Training ${String(this.$route.params.id).split('-')[1]}`,
                })
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
    clearRecentRows()
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
    expect(wrapper.get('[data-test="nav-model-projects"]').text()).toContain('模型项目')
    expect(wrapper.get('[data-test="nav-hyperparameter-templates"]').text()).toContain('超参数模板')
    expect(wrapper.get('[data-test="nav-training-tasks"]').text()).toContain('训练任务')
    expect(wrapper.findAll('[data-test="recent-model-project"]')).toHaveLength(2)
    expect(wrapper.findAll('[data-test="recent-training-task"]')).toHaveLength(2)
    for (const selector of [
      '[data-test="nav-projects"]',
      '[data-test="nav-model-projects"]',
      '[data-test="nav-hyperparameter-templates"]',
      '[data-test="nav-training-tasks"]',
    ]) {
      expect(wrapper.get(selector).classes()).toContain('app-nav-entry')
    }
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

  it('keeps model and training shortcut order stable for the app shell session', async () => {
    localStorage.setItem('vdm.recent-model-projects', JSON.stringify([
      { id: 'model-2', name: 'Model 2', visited_at: 20 },
      { id: 'model-1', name: 'Model 1', visited_at: 10 },
    ]))
    localStorage.setItem('vdm.recent-training-tasks', JSON.stringify([
      { id: 'training-2', name: 'Training 2', visited_at: 20 },
      { id: 'training-1', name: 'Training 1', visited_at: 10 },
    ]))
    const { router, wrapper } = await mountShell()

    await router.push('/model-projects/model-1')
    await flushPromises()
    await router.push('/training-tasks/training-1')
    await flushPromises()
    await router.push('/projects')
    await flushPromises()

    expect(wrapper.findAll('[data-test="recent-model-project"]').map((item) => item.text()))
      .toEqual(['Model 2', 'Model 1'])
    expect(wrapper.findAll('[data-test="recent-training-task"]').map((item) => item.text()))
      .toEqual(['Training 2', 'Training 1'])
    expect(JSON.parse(localStorage.getItem('vdm.recent-model-projects') ?? '[]')[0].id)
      .toBe('model-1')
    expect(JSON.parse(localStorage.getItem('vdm.recent-training-tasks') ?? '[]')[0].id)
      .toBe('training-1')
  })

  it('persists sidebar and project group preferences', async () => {
    const { wrapper } = await mountShell()

    const sidebarToggle = wrapper.get('[data-test="sidebar-toggle"]')
    expect(sidebarToggle.attributes('aria-label')).toBe('收起侧栏')
    expect(sidebarToggle.find('.el-icon').exists()).toBe(true)
    await sidebarToggle.trigger('click')
    expect(sidebarToggle.attributes('aria-label')).toBe('展开侧栏')
    expect(sidebarToggle.find('.el-icon').exists()).toBe(true)
    await wrapper.get('[data-test="project-group-toggle"]').trigger('click')

    expect(localStorage.getItem('vdm.sidebar-collapsed')).toBe('true')
    expect(localStorage.getItem('vdm.nav-projects-open')).toBe('false')
    expect(wrapper.get('[data-test="project-group-toggle"]').attributes('aria-expanded')).toBe('false')
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
    expect(wrapper.find('[data-test="nav-projects"] .app-sidebar-icon .el-icon').exists()).toBe(true)
    expect(wrapper.find('[data-test="nav-admin-users"] .app-sidebar-icon .el-icon').exists()).toBe(true)

    await wrapper.get('[data-test="sidebar-toggle"]').trigger('click')

    expect(wrapper.get('.app-shell').classes()).toContain('app-shell--collapsed')
    expect(wrapper.get('[data-test="brand"] .app-sidebar-icon').text()).toBe('VDM')
  })

  it('renders real links for navigable breadcrumb levels', async () => {
    const { router, wrapper } = await mountShell()

    expect(wrapper.get('[data-test="breadcrumb-section"]').attributes('href')).toBe('/projects')
    expect(wrapper.get('[data-test="breadcrumb-page"]').text()).toBe('全部项目')

    await router.push('/projects/project-1/videos')
    await flushPromises()

    expect(wrapper.get('[data-test="breadcrumb-section"]').attributes('href')).toBe('/projects')
    expect(wrapper.get('.app-breadcrumb a[href="/projects/project-1/videos"]').text()).toBe('Project 1')
    expect(wrapper.get('[data-test="breadcrumb-page"]').text()).toBe('原始数据')
    expect(wrapper.find('.app-sidebar-backdrop').exists()).toBe(false)
  })

  it('routes and signs out through the overlay user menu commands', async () => {
    const { router, wrapper } = await mountShell()
    const dropdown = wrapper.getComponent({ name: 'ElDropdown' })

    expect(wrapper.find('details.user-menu').exists()).toBe(false)
    dropdown.vm.$emit('command', 'account')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/account')

    markRecentRow('projects', 'project-1')
    expect(isRecentRow('projects', 'project-1')).toBe(true)

    dropdown.vm.$emit('command', 'logout')
    await flushPromises()
    expect(logout).toHaveBeenCalledOnce()
    expect(isRecentRow('projects', 'project-1')).toBe(false)
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
