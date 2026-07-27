import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AnnotationWorkbenchView from './AnnotationWorkbenchView.vue'

const mocks = vi.hoisted(() => ({
  routerPush: vi.fn(),
  routerReplace: vi.fn(),
  getProject: vi.fn(),
  listVideos: vi.fn(),
  listLabels: vi.fn(),
  listFrames: vi.fn(),
  setFramesEnabled: vi.fn(),
  getFrameAnnotations: vi.fn(),
  replaceFrameAnnotations: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'project-id', videoId: 'video-id' } }),
  useRouter: () => ({ push: mocks.routerPush, replace: mocks.routerReplace }),
}))
vi.mock('../api/projects', () => ({ getProject: mocks.getProject }))
vi.mock('../api/labels', () => ({ listLabels: mocks.listLabels }))
vi.mock('../api/media', () => ({
  listVideos: mocks.listVideos,
  listFrames: mocks.listFrames,
  setFramesEnabled: mocks.setFramesEnabled,
  frameImageUrl: (_project: string, _video: string, frame: string) => `/frames/${frame}`,
}))
vi.mock('../api/annotations', () => ({
  getFrameAnnotations: mocks.getFrameAnnotations,
  replaceFrameAnnotations: mocks.replaceFrameAnnotations,
}))

const CanvasStub = defineComponent({
  emits: ['change'],
  template: '<button data-test="canvas-change" @click="$emit(\'change\', [{ id: \'box-id\', label_id: \'label-id\', x_min: 1, y_min: 2, x_max: 30, y_max: 40, source: \'manual\', confidence: null }])">change</button>',
})

const project = {
  id: 'project-id',
  name: '安全帽',
  description: '',
  creator_id: 'creator-id',
  creator_username: 'creator',
  role: 'editor',
  version: 1,
  created_at: '',
  updated_at: '',
}
const video = {
  id: 'video-id',
  source_type: 'local',
  title: '园区监控',
  source_name: 'camera.mp4',
  source_url: null,
  duration: 10,
  width: 1920,
  height: 1080,
  fps: 25,
  total_frames: 250,
  file_size: 1000,
  status: 'ready',
  enabled: true,
  version: 1,
  created_at: '',
  updated_at: '',
  sampling: {
    id: 'plan-id', state: 'sampled', mode: 'target_frames', parameters: {},
    output_format: 'jpg', output_quality: 2, computed_interval: 100,
    expected_frames: 2, extracted_frames: 2, enabled_frames: 2,
    version: 1, applied_version: 1, generation: 1, frame_revision: 1,
    updated_at: '',
  },
  latest_task: null,
}
const frames = [1, 2].map((sequence) => ({
  id: `frame-${sequence}`,
  sequence,
  source_frame_index: sequence - 1,
  time_offset: (sequence - 1) / 25,
  enabled: true,
  file_size: 2048,
  created_at: '',
}))

beforeEach(() => {
  document.body.innerHTML = '<div id="focus-header-tools"></div>'
  for (const value of Object.values(mocks)) value.mockReset()
  mocks.getProject.mockResolvedValue(project)
  mocks.listVideos.mockResolvedValue({ items: [video], page: 1, page_size: 999, total: 1 })
  mocks.listLabels.mockResolvedValue([
    { id: 'label-id', name: 'helmet', description_zh: '安全帽', color: '#16866f', sort_order: 0, enabled: true, version: 1, created_at: '', updated_at: '' },
  ])
  mocks.listFrames.mockResolvedValue({
    items: frames, page: 1, page_size: 200, total: 2, sampling: video.sampling,
  })
  mocks.getFrameAnnotations.mockImplementation(
    (_project: string, _video: string, frameId: string) =>
      Promise.resolve({ frame_id: frameId, annotation_revision: 1, items: [] }),
  )
  mocks.replaceFrameAnnotations.mockImplementation(
    (_project: string, _video: string, value: { frame_id: string; annotation_revision: number; items: unknown[] }) =>
      Promise.resolve({ ...value, annotation_revision: value.annotation_revision + 1 }),
  )
})

afterEach(() => { document.body.innerHTML = '' })

describe('AnnotationWorkbenchView', () => {
  it('saves a dirty frame once before switching and before closing', async () => {
    const wrapper = mount(AnnotationWorkbenchView, {
      attachTo: document.body,
      global: {
        stubs: {
          AnnotationCanvas: CanvasStub,
          ElSelect: true,
          ElOption: true,
          ElInputNumber: true,
          ElSwitch: true,
          ElDialog: true,
        },
      },
    })
    await flushPromises()

    expect(document.querySelector('[data-test="frame-counter"]')?.textContent).toContain('1 / 2')
    await wrapper.get('[data-test="canvas-change"]').trigger('click')
    await wrapper.get('[data-test="next-frame"]').trigger('click')
    await flushPromises()
    expect(mocks.replaceFrameAnnotations).toHaveBeenCalledTimes(1)
    expect(document.querySelector('[data-test="frame-counter"]')?.textContent).toContain('2 / 2')

    await wrapper.get('[data-test="canvas-change"]').trigger('click')
    document.querySelector<HTMLElement>('[data-test="close-annotation"]')?.click()
    await flushPromises()
    expect(mocks.replaceFrameAnnotations).toHaveBeenCalledTimes(2)
    expect(mocks.routerPush).toHaveBeenCalledWith('/projects/project-id/videos')
  })

  it('redirects viewers instead of opening annotation controls', async () => {
    mocks.getProject.mockResolvedValueOnce({ ...project, role: 'viewer' })
    mount(AnnotationWorkbenchView, { global: { stubs: { AnnotationCanvas: CanvasStub } } })
    await flushPromises()

    expect(mocks.routerReplace).toHaveBeenCalledWith('/projects/project-id/videos')
    expect(mocks.getFrameAnnotations).not.toHaveBeenCalled()
  })
})
