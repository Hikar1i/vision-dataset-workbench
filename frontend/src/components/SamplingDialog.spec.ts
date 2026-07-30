import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import SamplingDialog from './SamplingDialog.vue'

const video = {
  id: 'video-id', short_code: 'TESTV001', source_type: 'local' as const, title: 'video',
  source_name: 'video.mp4', source_url: null, duration: 10, width: 1920, height: 1080,
  fps: 25, total_frames: 250, file_size: 1024, status: 'ready' as const, enabled: true,
  version: 1, created_at: '', updated_at: '', sampling: null, latest_task: null,
  has_annotations: false,
}

describe('SamplingDialog', () => {
  it('saves predictable defaults and switches PNG quality', async () => {
    const batch = { accepted: [{ video_id: 'video-id', plan: { expected_frames: 50 } }], rejected: [] }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => batch })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(SamplingDialog, {
      props: { modelValue: true, projectId: 'project-id', videos: [video] },
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
    expect(body.overwrite_level).toBe('none')
    expect(wrapper.emitted('submitted')?.[0]).toEqual([batch])
  })

  it('prefills configured plans and locks sampled targets until forced', async () => {
    const sampled = {
      ...video,
      sampling: {
        id: 'plan-id', state: 'sampled' as const, mode: 'frame_interval' as const,
        parameters: { interval: 12 }, output_format: 'png' as const, output_quality: 6,
        computed_interval: 12, expected_frames: 20, extracted_frames: 20, enabled_frames: 18,
        version: 1, applied_version: 1, generation: 1, frame_revision: 2, updated_at: '',
      },
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ accepted: [], rejected: [] }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(SamplingDialog, {
      props: { modelValue: true, projectId: 'project-id', videos: [sampled] },
      global: {
        plugins: [ElementPlus],
        stubs: { ElDialog: { props: ['modelValue'], template: '<section><slot/><slot name="footer"/></section>' } },
      },
    })

    expect(wrapper.get('[data-test="sampling-form"]').attributes('data-locked')).toBe('true')
    expect(wrapper.get('[data-test="save-sampling"]').text()).toBe('覆盖保存')
    await wrapper.get('[data-test="force-sampling-overwrite"] input').setValue(true)
    await wrapper.get('[data-test="save-sampling"]').trigger('click')
    await flushPromises()
    const body = JSON.parse(String(fetchMock.mock.calls[0][1].body))
    expect(body.parameters).toEqual({ interval: 12 })
    expect(body.overwrite_level).toBe('sampled')
  })
})
