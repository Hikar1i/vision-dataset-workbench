import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import OverviewView from './OverviewView.vue'

const { getOverview } = vi.hoisted(() => ({ getOverview: vi.fn() }))
vi.mock('../api/overview', () => ({ getOverview }))
vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), dispose: vi.fn() }) }))

const overview = {
  projects: 1,
  videos: 2,
  model_projects: 3,
  training_tasks: 4,
  running_tasks: { own: 0, global: 1 },
  task_status: [{ status: 'running', count: 1 }],
  host: { hostname: 'host', note: '主机标识已脱敏' },
}

beforeEach(() => getOverview.mockReset())

describe('OverviewView', () => {
  it('keeps failures compact and reloads the dashboard', async () => {
    getOverview.mockRejectedValueOnce(new Error('请求失败')).mockResolvedValueOnce(overview)
    const wrapper = mount(OverviewView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.get('[data-test="overview-error"]').text()).toContain('请求失败')
    await wrapper.get('[data-test="overview-refresh"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="overview-stats"]').text()).toContain('1')
    expect(wrapper.find('[data-test="overview-error"]').exists()).toBe(false)
  })
})
