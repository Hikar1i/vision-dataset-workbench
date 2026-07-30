import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, it, vi } from 'vitest'

import ExportDatasetDialog from './ExportDatasetDialog.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

it('loads project scope and submits an independently ordered label snapshot', async () => {
  const fetchMock = vi.fn().mockImplementation((path: string, init?: RequestInit) => {
    if (path.endsWith('/labels')) {
      return Promise.resolve({
        ok: true,
        json: async () => [
          { id: 'person-label', name: 'person', enabled: true, color: '#16866f', sort_order: 0 },
          { id: 'car-label', name: 'car', enabled: false, color: '#e85d4a', sort_order: 1 },
        ],
      })
    }
    if (path.includes('/videos?')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          items: [
            { id: 'video-1', status: 'ready', enabled: true, sampling: { extracted_frames: 50, enabled_frames: 48 } },
            { id: 'video-2', status: 'ready', enabled: false, sampling: { extracted_frames: 20, enabled_frames: 20 } },
          ],
          page: 1,
          page_size: 999,
          total: 2,
        }),
      })
    }
    expect(init?.method).toBe('POST')
    return Promise.resolve({
      ok: true,
      json: async () => ({ id: 'export-id', status: 'queued' }),
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(ExportDatasetDialog, {
    attachTo: document.body,
    props: { modelValue: true, projectId: 'project-id' },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  const body = new DOMWrapper(document.body)

  expect(body.text()).toContain('预计参与 1 个视频 · 48 个启用帧')
  await body.get('[data-test="dataset-name"]').setValue('训练集 v1')
  await body.get('[data-test="manual-mode"]').trigger('click')
  await flushPromises()
  await body.get('[data-test="label-enabled-person"]').trigger('click')
  expect(body.get('[data-test="submit-export"]').attributes('disabled')).toBeDefined()
  await body.get('[data-test="label-enabled-car"]').trigger('click')
  await body.get('[data-test="move-up-car"]').trigger('click')
  await body.get('[data-test="train-ratio"] input').setValue('0.6')
  await body.get('[data-test="submit-export"]').trigger('click')
  await flushPromises()

  const request = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
  const payload = JSON.parse(String(request?.[1]?.body))
  expect(payload).toEqual({
    name: '训练集 v1',
    train_ratio: 0.6,
    labels: [
      { source_label_id: 'car-label', name: 'car', mapping: 0, enabled: true },
      { source_label_id: 'person-label', name: 'person', mapping: 1, enabled: false },
    ],
  })
  expect(wrapper.emitted('submitted')?.[0]?.[0]).toMatchObject({ id: 'export-id' })
  expect(wrapper.emitted('update:modelValue')).toContainEqual([false])
})
