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

  it('surfaces the rejection reason instead of silently keeping the dialog open', async () => {
    // 后端把非法参数放进 rejected 而不是抛错。弹窗若只是不关闭，用户看不出
    // 哪里填错了，还会以为已经保存。
    const batch = {
      accepted: [],
      rejected: [{ input: 'video-id', reason: '目标帧数范围不合法', code: 'invalid_sampling' }],
    }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => batch })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(SamplingDialog, {
      props: { modelValue: true, projectId: 'project-id', videos: [video] },
      global: {
        plugins: [ElementPlus],
        stubs: { ElDialog: { props: ['modelValue'], template: '<section><slot/><slot name="footer"/></section>' } },
      },
    })

    await wrapper.get('[data-test="save-sampling"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('目标帧数范围不合法')
    // 没有一个视频保存成功时不得关闭弹窗，否则改动凭空消失
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.emitted('submitted')?.[0]).toEqual([batch])
  })
})
