import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElNotification } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { logout } from '../api/auth'
import { getCapabilities } from '../api/capabilities'
import { listProjects } from '../api/projects'
import { listModelProjects } from '../api/models'
import { listTrainingTasks } from '../api/training'
import { clearRecentRows, isRecentRow, markRecentRow } from '../ui/recentRows'
import AppShell from './AppShell.vue'
import TaskCenterDrawer from '../components/TaskCenterDrawer.vue'

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
  listProjects: vi.fn(),
}))
vi.mock('../api/capabilities', () => ({
  getCapabilities: vi.fn(),
}))
vi.mock('../api/models', () => ({
  listModelProjects: vi.fn(),
}))
vi.mock('../api/training', () => ({
  listTrainingTasks: vi.fn(),
}))

const readyCapabilities = {
  gpu: { available: true, reason: null, devices: [] },
  pytorch_cuda: { available: true, reason: null },
  features: {
    manual_annotation: { available: true, reason: null },
    yolo_auto_annotation: { available: true, reason: null },
    model_training: { available: true, reason: null },
    onnx_export: { available: true, reason: null },
    onnx_inference: { available: true, reason: null },
    tensorrt: { available: true, reason: null },
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
            component: { template: '<div />' },
          },
          {
            path: 'training-tasks/:id',
            component: { template: '<div />' },
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
    vi.mocked(listProjects).mockReset().mockResolvedValue({
      items: [
        { id: 'project-0', name: 'Project 0', updated_at: '2026-09-01T00:00:00Z' },
        { id: 'project-3', name: 'Project 3', updated_at: '2026-09-04T00:00:00Z' },
        { id: 'project-1', name: 'Project 1', updated_at: '2026-09-06T00:00:00Z' },
        { id: 'project-5', name: 'Project 5', updated_at: '2026-09-02T00:00:00Z' },
        { id: 'project-2', name: 'Project 2', updated_at: '2026-09-05T00:00:00Z' },
        { id: 'project-4', name: 'Project 4', updated_at: '2026-09-03T00:00:00Z' },
      ],
      total: 6,
      page: 1,
      page_size: 6,
    } as never)
    vi.mocked(listModelProjects).mockReset().mockResolvedValue([
      { id: 'model-1', name: 'Model 1', updated_at: '2026-09-01T00:00:00Z' },
      { id: 'model-2', name: 'Model 2', updated_at: '2026-09-02T00:00:00Z' },
    ] as never)
    vi.mocked(listTrainingTasks).mockReset().mockResolvedValue([
      {
        id: 'training-2', name: 'Training 2', last_run_at: null,
        updated_at: '2026-09-19T00:00:00Z',
      },
      {
        id: 'training-1', name: 'Training 1', last_run_at: '2026-09-20T00:00:00Z',
        updated_at: '2026-09-21T00:00:00Z',
      },
    ] as never)
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
  })

  it('shows implemented navigation and at most five project shortcuts', async () => {
    const { wrapper } = await mountShell()

    expect(wrapper.get('[data-test="brand"]').text()).toBe('VDM')
    expect(wrapper.get('[data-test="nav-projects"]').text()).toContain('数据集项目')
    expect(wrapper.findAll('[data-test="recent-project"]')).toHaveLength(5)
    expect(wrapper.findAll('[data-test="recent-project"]').map((item) => item.text()))
      .toEqual(['Project 1', 'Project 2', 'Project 3', 'Project 4', 'Project 5'])
    expect(wrapper.get('[data-test="nav-model-projects"]').text()).toContain('模型项目')
    expect(wrapper.get('[data-test="nav-hyperparameter-templates"]').text()).toContain('超参数模板')
    expect(wrapper.get('[data-test="nav-training-tasks"]').text()).toContain('训练任务')
    expect(wrapper.findAll('[data-test="recent-model-project"]')).toHaveLength(2)
    expect(wrapper.findAll('[data-test="recent-training-task"]')).toHaveLength(2)
    expect(wrapper.findAll('[data-test="recent-model-project"]').map((item) => item.text()))
      .toEqual(['Model 2', 'Model 1'])
    expect(wrapper.findAll('[data-test="recent-training-task"]').map((item) => item.text()))
      .toEqual(['Training 1', 'Training 2'])
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

  it('refreshes server-ranked shortcuts after navigation and task completion', async () => {
    const { router, wrapper } = await mountShell()
    vi.mocked(listProjects).mockResolvedValue({
      items: [{ id: 'project-new', name: 'Project new', updated_at: '2026-09-30T00:00:00Z' }],
      total: 1, page: 1, page_size: 5,
    } as never)

    await router.push('/account')
    await flushPromises()

    expect(wrapper.findAll('[data-test="recent-project"]').map((item) => item.text()))
      .toEqual(['Project new'])

    vi.mocked(listTrainingTasks).mockResolvedValue([{
      id: 'training-new', name: 'Training new', last_run_at: '2026-09-30T01:00:00Z',
      updated_at: '2026-09-30T01:00:00Z',
    }] as never)
    wrapper.findComponent(TaskCenterDrawer).vm.$emit('settled', [])
    await flushPromises()

    expect(wrapper.findAll('[data-test="recent-training-task"]').map((item) => item.text()))
      .toEqual(['Training new'])

    vi.mocked(listProjects).mockRejectedValueOnce(new Error('offline'))
    await router.push('/admin/users')
    await flushPromises()
    expect(wrapper.findAll('[data-test="recent-project"]').map((item) => item.text()))
      .toEqual(['Project new'])
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

  it('removes a deleted project from the current sidebar', async () => {
    const { wrapper } = await mountShell()

    await wrapper.get('[data-test="emit-project-deleted"]').trigger('click')

    expect(wrapper.findAll('[data-test="recent-project"]').map((item) => item.text()))
      .not.toContain('Project 1')
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

  it('groups new terminal task notifications and keeps cancellations quiet', async () => {
    vi.useFakeTimers()
    const success = vi.spyOn(ElNotification, 'success')
    const error = vi.spyOn(ElNotification, 'error')
    const { wrapper } = await mountShell()
    const drawer = wrapper.findComponent(TaskCenterDrawer)
    const base = {
      project_id: 'project-1',
      model_project_id: null,
      video_id: null,
      type: 'extract_frames' as const,
      progress: 100,
      error: null,
      result: null,
      cancel_requested: false,
      attempts: 1,
      retry_of_id: null,
      created_at: '2026-07-24T00:00:00Z',
      started_at: '2026-07-24T00:00:01Z',
      finished_at: '2026-07-24T00:00:02Z',
      updated_at: '2026-07-24T00:00:02Z',
      project_name: 'Project 1',
      resource_kind: 'project' as const,
      resource_name: 'Project 1',
      can_manage: true,
    }
    drawer.vm.$emit('settled', [
      { ...base, id: 'success-1', status: 'succeeded' },
      { ...base, id: 'success-2', status: 'succeeded' },
      { ...base, id: 'failed-1', status: 'failed', error: 'failed' },
      { ...base, id: 'canceled-1', status: 'canceled' },
    ])
    await flushPromises()

    expect(success).toHaveBeenCalledWith(expect.objectContaining({
      title: '2 个后台任务已完成',
      duration: 4500,
    }))
    expect(error).toHaveBeenCalledWith(expect.objectContaining({
      title: '后台任务执行失败',
      duration: 8000,
    }))
    expect(wrapper.get('[data-test="task-center"]').classes()).toContain('is-pulsing')
    expect(wrapper.find('[data-test="task-center"] .task-center-bell').exists()).toBe(true)
    vi.useRealTimers()
    wrapper.unmount()
  })
})
