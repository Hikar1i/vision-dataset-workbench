import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import BatchAnnotationDialog from './BatchAnnotationDialog.vue'

const mocks = vi.hoisted(() => ({
  listProjects: vi.fn(), listModels: vi.fn(), listRemote: vi.fn(), create: vi.fn(),
}))
vi.mock('../api/models', () => ({
  listModelProjects: mocks.listProjects,
  listModelProjectModels: mocks.listModels,
  listXAnyLabelingModels: mocks.listRemote,
  createProjectBatchAutoAnnotation: mocks.create,
}))

const baseVideo = {
  id: 'video-new', short_code: 'NEW', source_type: 'local' as const, title: 'new.mp4',
  source_name: 'new.mp4', source_url: null, duration: 1, width: 640, height: 480,
  fps: 25, total_frames: 25, file_size: 100, status: 'ready' as const, enabled: true,
  version: 1, created_at: '2026-08-07T00:00:00Z', updated_at: '2026-08-07T00:00:00Z',
  sampling: null, latest_task: null, has_annotations: false,
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.listProjects.mockResolvedValue([{ id: 'project-models', name: '检测模型' }])
  mocks.listModels.mockResolvedValue([{ id: 'model-id', name: 'YOLO11n' }])
  mocks.listRemote.mockResolvedValue([])
})
afterEach(() => { document.body.innerHTML = '' })

function mountDialog(scope: 'unannotated' | 'all') {
  return mount(BatchAnnotationDialog, {
    props: {
      modelValue: true,
      projectId: 'project-id',
      scope,
      videos: scope === 'all'
        ? [baseVideo, { ...baseVideo, id: 'video-old', has_annotations: true }]
        : [baseVideo],
    },
    global: { plugins: [ElementPlus] },
  })
}

describe('BatchAnnotationDialog', () => {
  it('keeps overwrite disabled for unannotated-only processing', async () => {
    const wrapper = mountDialog('unannotated')
    await flushPromises()

    expect(wrapper.text()).toContain('将处理 1 个未标注视频')
    expect(wrapper.find('[data-test="annotation-risk-confirm"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="annotation-overwrite"]').classes()).toContain('is-disabled')
    expect(wrapper.get('[data-test="annotation-create-task"]').attributes('disabled')).toBeUndefined()
  })

  it('gates all settings until the user confirms annotated-video risk', async () => {
    const wrapper = mountDialog('all')
    await flushPromises()

    expect(wrapper.text()).toContain('其中 1 个已有标注')
    expect(wrapper.get('[data-test="annotation-create-task"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="annotation-risk-confirm"] input').setValue(true)
    await flushPromises()
    expect(wrapper.get('[data-test="annotation-create-task"]').attributes('disabled')).toBeUndefined()
  })
})
