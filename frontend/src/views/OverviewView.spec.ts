import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import OverviewView from './OverviewView.vue'

const { getOverview } = vi.hoisted(() => ({ getOverview: vi.fn() }))
vi.mock('../api/overview', () => ({ getOverview }))

const overview = {
  projects: 1,
  videos: 2,
  model_projects: 3,
  training_tasks: 4,
  running_tasks: { own: 0, global: 1 },
  task_status: [
    { status: 'running', count: 1 },
    { status: 'succeeded', count: 3 },
  ],
  host: { hostname: 'host', note: '主机标识已脱敏' },
}

const router = () => createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div />' } },
    { path: '/projects', component: { template: '<div />' } },
    { path: '/model-projects', component: { template: '<div />' } },
    { path: '/training-tasks', component: { template: '<div />' } },
  ],
})

const mountView = async () => {
  const instance = router()
  await instance.push('/')
  await instance.isReady()
  return mount(OverviewView, { global: { plugins: [ElementPlus, instance] } })
}

beforeEach(() => getOverview.mockReset())

describe('OverviewView', () => {
  it('keeps failures compact and reloads the dashboard', async () => {
    getOverview.mockRejectedValueOnce(new Error('请求失败')).mockResolvedValueOnce(overview)
    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.get('[data-test="overview-error"]').text()).toContain('请求失败')
    await wrapper.get('[data-test="overview-refresh"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="overview-stats"]').text()).toContain('1')
    expect(wrapper.find('[data-test="overview-error"]').exists()).toBe(false)
  })

  it('renders the status split natively with labels and totals, without echarts', async () => {
    getOverview.mockResolvedValueOnce(overview)
    const wrapper = await mountView()
    await flushPromises()

    const text = wrapper.text()
    // 后端只给状态英文码，条形图必须自己补中文名与合计
    expect(text).toContain('进行中')
    expect(text).toContain('全部完成')
    expect(text).toContain('合计')
    expect(wrapper.findAll('[role="progressbar"]')).toHaveLength(2)
  })

  it('turns the running counts into a sentence in the header', async () => {
    getOverview.mockResolvedValueOnce(overview)
    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.get('[data-test="page-stat"]').text())
      .toBe('全局 1 个训练进行中，其中没有你的任务')
  })

  it('links each metric to the list it summarises', async () => {
    getOverview.mockResolvedValueOnce(overview)
    const wrapper = await mountView()
    await flushPromises()

    const hrefs = wrapper.findAll('[data-test="overview-stats"] a')
      .map((node) => node.attributes('href'))
    expect(hrefs).toContain('/projects')
    expect(hrefs).toContain('/model-projects')
    expect(hrefs).toContain('/training-tasks')
  })
})
