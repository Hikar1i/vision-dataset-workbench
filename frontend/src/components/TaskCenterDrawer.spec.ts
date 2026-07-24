import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import TaskCenterDrawer from './TaskCenterDrawer.vue'

const failedTask = {
  id: 'task-id',
  project_id: 'project-id',
  project_name: 'Smoke Dataset',
  can_manage: true,
  video_id: 'video-id',
  type: 'extract_frames',
  status: 'failed',
  progress: 30,
  error: 'network failed',
  result: null,
  cancel_requested: false,
  attempts: 1,
  retry_of_id: null,
  created_at: '2026-07-24T00:00:00Z',
  started_at: '2026-07-24T00:00:01Z',
  finished_at: '2026-07-24T00:00:02Z',
  updated_at: '2026-07-24T00:00:02Z',
} as const

beforeEach(() => {
  localStorage.clear()
  vi.useFakeTimers()
})
afterEach(() => vi.useRealTimers())

describe('TaskCenterDrawer', () => {
  it('marks terminal tasks unread and uses their project for retry', async () => {
    const fetchMock = vi.fn().mockImplementation((_path: string, init?: RequestInit) =>
      Promise.resolve({
        ok: true,
        status: init?.method === 'POST' ? 201 : 200,
        json: async () =>
          init?.method === 'POST'
            ? { ...failedTask, id: 'retry-id', status: 'queued' }
            : {
                items: [failedTask],
                page: 1,
                page_size: 50,
                total: 1,
                latest_terminal_at: failedTask.updated_at,
              },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(TaskCenterDrawer, {
      props: { modelValue: false },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    expect(wrapper.emitted('unread')?.at(-1)).toEqual([true])

    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    expect(wrapper.text()).toContain('Smoke Dataset')
    expect(wrapper.emitted('unread')?.at(-1)).toEqual([false])
    await wrapper.get('[data-test="retry-task-id"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/projects/project-id/tasks/task-id/retry',
      expect.objectContaining({ method: 'POST' }),
    )
    wrapper.unmount()
  })
})
