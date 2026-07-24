import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import SamplingDialog from './SamplingDialog.vue'

describe('SamplingDialog', () => {
  it('saves predictable defaults and switches PNG quality', async () => {
    const batch = { accepted: [{ video_id: 'video-id', plan: { expected_frames: 50 } }], rejected: [] }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => batch })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(SamplingDialog, {
      props: { modelValue: true, projectId: 'project-id', videoIds: ['video-id'] },
      global: {
        plugins: [ElementPlus],
        stubs: { ElDialog: { props: ['modelValue'], template: '<section><slot/><slot name="footer"/></section>' } },
      },
    })
    await wrapper.get('[data-test="output-format"]').setValue('png')
    expect((wrapper.get('[data-test="output-quality"]').element as HTMLInputElement).value).toBe('6')
    await wrapper.get('[data-test="save-sampling"]').trigger('click')
    await flushPromises()
    const body = JSON.parse(String(fetchMock.mock.calls[0][1].body))
    expect(body.parameters).toEqual({ minimum: 50, maximum: 200 })
    expect(body.output_format).toBe('png')
    expect(wrapper.emitted('submitted')?.[0]).toEqual([batch])
  })
})
