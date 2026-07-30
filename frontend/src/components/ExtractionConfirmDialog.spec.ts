import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ExtractionConfirmDialog from './ExtractionConfirmDialog.vue'

const video = {
  id: 'video-id', short_code: 'TESTV001', source_type: 'local' as const, title: 'video',
  source_name: 'video.mp4', source_url: null, duration: 10, width: 1920, height: 1080,
  fps: 25, total_frames: 250, file_size: 1024, status: 'ready' as const, enabled: true,
  version: 1, created_at: '', updated_at: '', latest_task: null, has_annotations: false,
  sampling: {
    id: 'plan-id', state: 'sampled' as const, mode: 'target_frames' as const,
    parameters: { minimum: 50, maximum: 200 }, output_format: 'jpg' as const,
    output_quality: 2, computed_interval: 5, expected_frames: 50, extracted_frames: 50,
    enabled_frames: 50, version: 1, applied_version: 1, generation: 1,
    frame_revision: 1, updated_at: '',
  },
}

afterEach(() => {
  vi.useRealTimers()
  document.body.innerHTML = ''
})

const mountDialog = (target = video) => mount(ExtractionConfirmDialog, {
  props: { modelValue: true, videos: [target] },
  global: {
    plugins: [ElementPlus],
    stubs: { ElDialog: { props: ['modelValue'], template: '<section><slot/><slot name="footer"/></section>' } },
  },
})

describe('ExtractionConfirmDialog', () => {
  it('confirms pristine sampled videos without a countdown', async () => {
    const wrapper = mountDialog()
    await wrapper.get('[data-test="confirm-overwrite"]').trigger('click')
    expect(wrapper.emitted('confirmed')?.[0]).toEqual(['light'])
  })

  it('requires three seconds when annotations or screening changes exist', async () => {
    vi.useFakeTimers()
    const wrapper = mountDialog({ ...video, has_annotations: true })
    expect(wrapper.get('[data-test="confirm-overwrite"]').attributes('disabled')).toBeDefined()
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(wrapper.get('[data-test="confirm-overwrite"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-test="confirm-overwrite"]').trigger('click')
    expect(wrapper.emitted('confirmed')?.[0]).toEqual(['destructive'])
  })
})
