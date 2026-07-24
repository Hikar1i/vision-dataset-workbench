import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectTaskDrawer from './ProjectTaskDrawer.vue'

const failedTask = {
  id: 'task-id',
  video_id: 'video-id',
  type: 'extract_frames',
  status: 'failed',
  progress: 30,
  error: 'network failed',
  result: null,
  cancel_requested: false,
  attempts: 1,
  retry_of_id: null,
  created_at: '2026-07-23T00:00:00Z',
  started_at: '2026-07-23T00:00:01Z',
  finished_at: '2026-07-23T00:00:02Z',
  updated_at: '2026-07-23T00:00:02Z',
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('ProjectTaskDrawer', () => {
  it('polls while open, retries failed tasks and clears its timer', async () => {
    const intervalSpy = vi.spyOn(globalThis, 'setInterval')
    const clearSpy = vi.spyOn(globalThis, 'clearInterval')
    const fetchMock = vi.fn().mockImplementation((_path: string, init?: RequestInit) =>
      Promise.resolve({
        ok: true,
        status: init?.method === 'POST' ? 201 : 200,
        json: async () =>
          init?.method === 'POST'
            ? { ...failedTask, id: 'retry-id', status: 'queued', retry_of_id: 'task-id' }
            : { items: [failedTask], page: 1, page_size: 50, total: 1 },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ProjectTaskDrawer, {
      props: { modelValue: true, projectId: 'project-id', canManage: true },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('network failed')
    expect(wrapper.text()).toContain('采样抽帧')
    await wrapper.get('[data-test="retry-task-id"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/projects/project-id/tasks/task-id/retry',
      expect.objectContaining({ method: 'POST' }),
    )
    const pollCall = intervalSpy.mock.calls.findIndex((call) => call[1] === 1000)
    const pollTimer = intervalSpy.mock.results[pollCall]?.value
    expect(pollCall).toBeGreaterThanOrEqual(0)
    wrapper.unmount()
    expect(clearSpy).toHaveBeenCalledWith(pollTimer)
  })
})
