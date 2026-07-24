import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import FramesDialog from './FramesDialog.vue'

const sampling = { frame_revision: 1, enabled_frames: 2, extracted_frames: 2 }
const page = { items: [{ id: 'frame-1', sequence: 1, source_frame_index: 0, time_offset: 0, enabled: true, created_at: '' }], page: 1, page_size: 50, total: 1, sampling }

function mountDialog(canEdit: boolean, fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal('fetch', fetchMock)
  return mount(FramesDialog, {
    props: { modelValue: true, projectId: 'project-id', videoId: 'video-id', title: 'video', canEdit },
    global: { plugins: [ElementPlus], stubs: { ElDialog: { template: '<section><slot/></section>' } } },
  })
}

describe('FramesDialog', () => {
  it('lets a viewer inspect images without filter controls', async () => {
    const wrapper = mountDialog(false, vi.fn().mockResolvedValue({ ok: true, json: async () => page }))
    await flushPromises()
    expect(wrapper.get('img').attributes('src')).toContain('/frames/frame-1/image')
    expect(wrapper.find('[data-test="restore-all"]').exists()).toBe(false)
  })

  it('sends one batch request for selected frames', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => page })
    const wrapper = mountDialog(true, fetchMock)
    await flushPromises()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('[data-test="disable-selected"]').trigger('click')
    await flushPromises()
    const call = fetchMock.mock.calls.find((item) => item[1]?.method === 'PUT')
    expect(JSON.parse(String(call?.[1].body)).frame_ids).toEqual(['frame-1'])
  })
})
