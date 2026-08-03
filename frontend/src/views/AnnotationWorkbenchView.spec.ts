import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
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
  getCurrentUser: vi.fn(),
  getCapabilities: vi.fn(),
  listInferenceModels: vi.fn(),
  listModelProjects: vi.fn(),
  listModelProjectModels: vi.fn(),
  getXAnyLabelingSetting: vi.fn(),
  listXAnyLabelingModels: vi.fn(),
  saveXAnyLabelingSetting: vi.fn(),
  runFrameAutoAnnotation: vi.fn(),
  createBatchAutoAnnotation: vi.fn(),
  registerInferenceModel: vi.fn(),
  confirmBatch: vi.fn(),
}))

vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal<typeof import('element-plus')>(),
  ElMessageBox: { confirm: mocks.confirmBatch },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'project-id', videoId: 'video-id' } }),
  useRouter: () => ({ push: mocks.routerPush, replace: mocks.routerReplace }),
}))
vi.mock('../api/projects', () => ({ getProject: mocks.getProject }))
vi.mock('../api/auth', () => ({ getCurrentUser: mocks.getCurrentUser }))
vi.mock('../api/capabilities', () => ({ getCapabilities: mocks.getCapabilities }))
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
vi.mock('../api/models', () => ({
  listModelProjects: mocks.listModelProjects,
  listModelProjectModels: mocks.listModelProjectModels,
  getXAnyLabelingSetting: mocks.getXAnyLabelingSetting,
  listXAnyLabelingModels: mocks.listXAnyLabelingModels,
  saveXAnyLabelingSetting: mocks.saveXAnyLabelingSetting,
  runFrameAutoAnnotation: mocks.runFrameAutoAnnotation,
  createBatchAutoAnnotation: mocks.createBatchAutoAnnotation,
  registerInferenceModel: mocks.registerInferenceModel,
}))

const CanvasStub = defineComponent({
  emits: ['change', 'request-category', 'view-change'],
  template: '<div><button data-test="canvas-change" @click="$emit(\'change\', [{ id: \'box-id\', label_id: \'label-id\', x_min: 1, y_min: 2, x_max: 30, y_max: 40, source: \'manual\', confidence: null }])">change</button><button data-test="request-category" @click="$emit(\'request-category\', { x_min: 10, y_min: 20, x_max: 110, y_max: 220 }, { x: 50, y: 60 })">draw</button><button data-test="view-change" @click="$emit(\'view-change\', { x_min: 100, y_min: 200, x_max: 900, y_max: 700 })">view</button></div>',
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
  short_code: 'TESTV001',
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
  localStorage.clear()
  for (const value of Object.values(mocks)) value.mockReset()
  mocks.confirmBatch.mockResolvedValue('confirm')
  mocks.getProject.mockResolvedValue(project)
  mocks.getCurrentUser.mockResolvedValue({
    id: 'editor-id', username: 'editor', status: 'active', is_system_admin: false,
  })
  mocks.getCapabilities.mockResolvedValue({
    gpu: { available: true, reason: null, devices: [] },
    pytorch_cuda: { available: true, reason: null },
    features: {
      manual_annotation: { available: true, reason: null },
      yolo_auto_annotation: { available: true, reason: null },
      model_training: { available: true, reason: null },
    },
  })
  mocks.listInferenceModels.mockResolvedValue([])
  mocks.listModelProjects.mockResolvedValue([{
    id: 'temporary-model-project',
    name: '临时模型项目',
    series_type: 'archive',
    system_key: 'temporary',
    created_at: '',
  }])
  mocks.listModelProjectModels.mockImplementation(() => mocks.listInferenceModels())
  mocks.getXAnyLabelingSetting.mockResolvedValue({
    configured: false,
    server_url: '',
    has_api_key: false,
    available: false,
  })
  mocks.listXAnyLabelingModels.mockResolvedValue([])
  mocks.listVideos.mockResolvedValue({ items: [video], page: 1, page_size: 999, total: 1 })
  mocks.listLabels.mockResolvedValue([
    { id: 'label-id', name: 'helmet', description_zh: '安全帽', color: '#16866f', sort_order: 0, enabled: true, version: 1, created_at: '', updated_at: '' },
  ])
  mocks.listFrames.mockResolvedValue({
    items: structuredClone(frames),
    page: 1,
    page_size: 200,
    total: 2,
    sampling: structuredClone(video.sampling),
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
    expect(wrapper.get('[data-test="crosshair-switch"]').attributes('modelvalue')).toBe('true')
    expect(wrapper.find('.image-info dl').exists()).toBe(true)
    expect(wrapper.get('.image-info dl dd').text()).toBe('TESTV001_frame_000001.jpg')
    expect(wrapper.get('.minimap-svg').attributes('viewBox')).toBe('0 0 1920 1080')
    await wrapper.get('[data-test="view-change"]').trigger('click')
    expect(wrapper.get('.viewport-box').attributes()).toMatchObject({
      x: '100', y: '200', width: '800', height: '500',
    })
    expect(wrapper.get('[data-test="toggle-all-boxes"]').attributes('title')).toBe('隐藏全部标注框')
    await wrapper.get('[data-test="image-info-toggle"]').trigger('click')
    expect(wrapper.find('.image-info dl').exists()).toBe(false)
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
    wrapper.unmount()
  })

  it('redirects viewers instead of opening annotation controls', async () => {
    mocks.getProject.mockResolvedValueOnce({ ...project, role: 'viewer' })
    const wrapper = mount(AnnotationWorkbenchView, { global: { stubs: { AnnotationCanvas: CanvasStub } } })
    await flushPromises()

    expect(mocks.routerReplace).toHaveBeenCalledWith('/projects/project-id/videos')
    expect(mocks.getFrameAnnotations).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps every expanded frame on a dedicated grid card', async () => {
    const wrapper = mount(AnnotationWorkbenchView, {
      global: {
        stubs: {
          AnnotationCanvas: CanvasStub,
          ServerVideoPicker: true,
          ElSelect: true,
          ElOption: true,
          ElInputNumber: true,
          ElSwitch: true,
          ElDialog: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('[title="展开全部采样帧"]').trigger('click')
    expect(wrapper.get('[data-test="frame-grid"]').classes()).toContain('frame-grid')
    expect(wrapper.findAll('[data-test="frame-grid-card"]')).toHaveLength(2)
    wrapper.unmount()
  })

  it('summarizes every frame with the current draft and expands or collapses every object group', async () => {
    mocks.listLabels.mockResolvedValueOnce([
      { id: 'label-id', name: 'helmet', description_zh: '安全帽', color: '#16866f', sort_order: 0, enabled: true, version: 1, created_at: '', updated_at: '' },
      { id: 'person-id', name: 'person', description_zh: '人员', color: '#c83f49', sort_order: 1, enabled: true, version: 1, created_at: '', updated_at: '' },
    ])
    const helmetBox = (id: string) => ({
      id, label_id: 'label-id', x_min: 1, y_min: 2, x_max: 30, y_max: 40,
      source: 'manual' as const, confidence: null,
    })
    const personBox = {
      id: 'person-box', label_id: 'person-id', x_min: 2, y_min: 3, x_max: 40, y_max: 50,
      source: 'manual' as const, confidence: null,
    }
    mocks.listFrames.mockResolvedValueOnce({
      items: [
        { ...frames[0], annotations: [helmetBox('saved-1'), helmetBox('saved-2')] },
        { ...frames[1], annotations: [personBox] },
      ],
      page: 1,
      page_size: 200,
      total: 2,
      sampling: structuredClone(video.sampling),
    })
    mocks.getFrameAnnotations.mockResolvedValueOnce({
      frame_id: 'frame-1',
      annotation_revision: 1,
      items: [helmetBox('saved-1'), helmetBox('saved-2')],
    })
    const wrapper = mount(AnnotationWorkbenchView, {
      global: { stubs: { AnnotationCanvas: CanvasStub, ElSwitch: true } },
    })
    await flushPromises()

    await wrapper.get('[data-test="canvas-change"]').trigger('click')
    document.querySelector<HTMLElement>('[data-test="stats-action"]')?.click()
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-test="all-box-count"]').text()).toContain('2')
    expect(wrapper.get('[data-test="stats-category-label-id"]').text()).toBe('helmet1')
    expect(wrapper.get('[data-test="stats-category-label-id"] dt').attributes('style')).toContain('rgb(22, 134, 111)')
    expect(wrapper.get('[data-test="stats-category-person-id"]').text()).toBe('person1')

    await wrapper.get('[data-test="expand-all-objects"]').trigger('click')
    expect(wrapper.findAll('.box-list')).toHaveLength(1)
    await wrapper.get('[data-test="collapse-all-objects"]').trigger('click')
    expect(wrapper.findAll('.box-list')).toHaveLength(0)
    wrapper.unmount()
  })

  it('keeps a pending rectangle until category confirmation or Escape', async () => {
    const wrapper = mount(AnnotationWorkbenchView, {
      global: { stubs: { AnnotationCanvas: CanvasStub, ElSwitch: true } },
    })
    await flushPromises()

    expect(wrapper.findAll('[data-test="stats-row"]').map((row) => row.text())).toEqual([
      '采样帧2',
      '启用帧2',
      '当前帧标注框0',
      '所有帧标注框0',
    ])
    expect(
      wrapper.get('[data-test="shortcut-list"]').findAll('dt').map((item) => item.text()),
    ).toEqual(expect.arrayContaining(['S', 'Y', 'L', 'H', 'P']))
    await wrapper.get('[data-test="request-category"]').trigger('click')
    expect(wrapper.find('[data-test="category-scrim"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="category-picker"]').exists()).toBe(true)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[data-test="category-picker"]').exists()).toBe(false)

    await wrapper.get('[data-test="request-category"]').trigger('click')
    await wrapper.get('[data-test="confirm-category"]').trigger('click')
    await wrapper.get('[data-test="next-frame"]').trigger('click')
    await flushPromises()
    expect(mocks.replaceFrameAnnotations.mock.calls[0]?.[2].items).toHaveLength(1)
    wrapper.unmount()
  })

  it('exits clicked pan mode and handles annotation shortcuts', async () => {
    mocks.listInferenceModels.mockResolvedValueOnce([{
      id: 'model-id', name: 'YOLO', kind: 'yolo', status: 'ready',
      source_name: 'model.pt', error: null, created_at: '', updated_at: '',
    }])
    mocks.getFrameAnnotations.mockResolvedValue({
      frame_id: 'frame-1',
      annotation_revision: 1,
      items: [{
        id: 'box-id', label_id: 'label-id', x_min: 1, y_min: 2, x_max: 30, y_max: 40,
        source: 'manual', confidence: null,
      }],
    })
    mocks.setFramesEnabled.mockResolvedValue({
      ...video.sampling, enabled_frames: 1, frame_revision: 2,
    })
    mocks.runFrameAutoAnnotation.mockResolvedValue({ items: [], created_labels: [] })
    const wrapper = mount(AnnotationWorkbenchView, {
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

    const panTool = wrapper.get('[data-test="pan-tool"]')
    await panTool.trigger('click')
    expect(panTool.classes()).toContain('active')
    await panTool.trigger('click')
    expect(panTool.classes()).not.toContain('active')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 's' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'y' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'h' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'p' }))
    await flushPromises()

    expect(mocks.setFramesEnabled).toHaveBeenCalledWith(
      'project-id', 'video-id', [{ frame_id: 'frame-1', enabled: false }], 1,
    )
    expect(wrapper.get('[data-test="reuse-label-switch"]').attributes('modelvalue')).toBe('true')
    expect(wrapper.get('[data-test="crosshair-switch"]').attributes('modelvalue')).toBe('false')
    expect(wrapper.get('[data-test="toggle-all-boxes"]').attributes('title')).toBe('显示全部标注框')
    expect(mocks.runFrameAutoAnnotation).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('reuses the remembered project label without opening the picker', async () => {
    localStorage.setItem(
      'vdm:annotation-preference:project-id',
      JSON.stringify({ reuse: true, labelId: 'label-id' }),
    )
    const wrapper = mount(AnnotationWorkbenchView, {
      global: { stubs: { AnnotationCanvas: CanvasStub, ElSwitch: true } },
    })
    await flushPromises()

    await wrapper.get('[data-test="request-category"]').trigger('click')
    expect(wrapper.find('[data-test="category-picker"]').exists()).toBe(false)
    await wrapper.get('[data-test="next-frame"]').trigger('click')
    await flushPromises()
    expect(mocks.replaceFrameAnnotations.mock.calls[0]?.[2].items).toHaveLength(1)
    wrapper.unmount()
  })

  it('adds single inference to the draft and queues batch inference after saving', async () => {
    const model = {
      id: 'model-id', name: 'YOLO', kind: 'yolo', status: 'ready',
      source_name: 'model.pt', error: null, created_at: '', updated_at: '',
    }
    mocks.listInferenceModels.mockResolvedValueOnce([model])
    mocks.runFrameAutoAnnotation.mockResolvedValue({
      items: [{
        id: 'auto-box', label_id: 'label-id', label_name: 'helmet',
        x_min: 10, y_min: 20, x_max: 110, y_max: 220,
        source: 'model', confidence: 0.9,
      }],
      created_labels: [],
    })
    mocks.createBatchAutoAnnotation.mockResolvedValue({
      id: 'auto-task', project_id: 'project-id', video_id: 'video-id',
      type: 'auto_annotate', status: 'queued', progress: 0, error: null,
      result: null, cancel_requested: false, attempts: 0, retry_of_id: null,
      created_at: '', started_at: null, finished_at: null, updated_at: '',
    })
    const wrapper = mount(AnnotationWorkbenchView, {
      global: {
        stubs: {
          AnnotationCanvas: CanvasStub,
          ServerVideoPicker: true,
          ElSelect: true,
          ElOption: true,
          ElInputNumber: true,
          ElSwitch: true,
          ElDialog: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.get('[data-test="overwrite-switch"]').attributes('disabled')).toBe('false')
    expect(document.querySelector('[data-test="stats-action"]')?.classList).toContain('primary-action')
    expect(wrapper.get('[data-test="run-single-auto"]').classes()).toContain('primary-action')
    expect(wrapper.get('[data-test="run-batch-auto"]').classes()).toContain('primary-action')
    await wrapper.get('[data-test="run-single-auto"]').trigger('click')
    await flushPromises()
    expect(mocks.runFrameAutoAnnotation).toHaveBeenCalledTimes(1)
    expect(mocks.runFrameAutoAnnotation.mock.calls[0]?.[3]).toMatchObject({
      source: 'local', model_id: 'model-id', remote_task_id: null,
    })
    await wrapper.get('[data-test="run-batch-auto"]').trigger('click')
    await flushPromises()
    expect(mocks.confirmBatch).toHaveBeenCalledWith(
      expect.stringContaining('2 个启用采样帧'),
      '确认批量自动标注',
      expect.objectContaining({ confirmButtonText: '确认运行' }),
    )
    expect(mocks.replaceFrameAnnotations).toHaveBeenCalledTimes(1)
    expect(mocks.createBatchAutoAnnotation).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('uses the configured X-AnyLabeling model as a remote source', async () => {
    mocks.listModelProjects.mockResolvedValueOnce([])
    mocks.getXAnyLabelingSetting.mockResolvedValueOnce({
      configured: true,
      server_url: 'http://127.0.0.1:44444',
      has_api_key: false,
      available: true,
    })
    mocks.listXAnyLabelingModels.mockResolvedValueOnce([{
      key: '["remote","grounding"]',
      model_id: 'remote',
      task_id: 'grounding',
      name: 'Remote / Grounding',
      batch_processing_mode: 'text_prompt',
    }])
    mocks.runFrameAutoAnnotation.mockResolvedValue({ items: [], created_labels: [] })
    const wrapper = mount(AnnotationWorkbenchView, {
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

    await wrapper.get('[data-test="run-single-auto"]').trigger('click')
    await flushPromises()

    expect(mocks.runFrameAutoAnnotation.mock.calls[0]?.[3]).toMatchObject({
      source: 'xanylabeling', model_id: 'remote', remote_task_id: 'grounding',
    })
    wrapper.unmount()
  })

  it('shows a blocking save overlay while a dirty frame is switching', async () => {
    let finishSave: ((value: unknown) => void) | undefined
    mocks.replaceFrameAnnotations.mockImplementationOnce(
      (_project: string, _video: string, value: { frame_id: string; annotation_revision: number; items: unknown[] }) =>
        new Promise((resolve) => {
          finishSave = () => resolve({ ...value, annotation_revision: value.annotation_revision + 1 })
        }),
    )
    const wrapper = mount(AnnotationWorkbenchView, {
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

    await wrapper.get('[data-test="canvas-change"]').trigger('click')
    await wrapper.get('[data-test="next-frame"]').trigger('click')
    expect(wrapper.get('[data-test="save-overlay"]').text()).toContain('保存并切换采样帧')

    finishSave?.({})
    await flushPromises()
    expect(wrapper.find('[data-test="save-overlay"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps All mutually exclusive with explicit auto-annotation categories', async () => {
    mocks.listInferenceModels.mockResolvedValueOnce([{
      id: 'model-id', name: 'YOLO', kind: 'yolo', status: 'ready',
      source_name: 'model.pt', error: null, created_at: '', updated_at: '',
    }])
    mocks.runFrameAutoAnnotation.mockResolvedValue({ items: [], created_labels: [] })
    const wrapper = mount(AnnotationWorkbenchView, {
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

    ;(wrapper.getComponent('[data-test="auto-categories"]') as VueWrapper).vm.$emit(
      'change', ['__all__', 'helmet'],
    )
    await wrapper.get('[data-test="run-single-auto"]').trigger('click')
    await flushPromises()
    expect(mocks.runFrameAutoAnnotation.mock.calls[0]?.[3].categories).toEqual(['helmet'])

    ;(wrapper.getComponent('[data-test="auto-categories"]') as VueWrapper).vm.$emit(
      'change', ['helmet', '__all__'],
    )
    await wrapper.get('[data-test="run-single-auto"]').trigger('click')
    await flushPromises()
    expect(mocks.runFrameAutoAnnotation.mock.calls[1]?.[3].categories).toEqual([])
    wrapper.unmount()
  })

  it('disables batch inference for a disabled video', async () => {
    mocks.listVideos.mockResolvedValueOnce({
      items: [{ ...video, enabled: false }], page: 1, page_size: 999, total: 1,
    })
    mocks.listInferenceModels.mockResolvedValueOnce([{
      id: 'model-id', name: 'YOLO', kind: 'yolo', status: 'ready',
      source_name: 'model.pt', error: null, created_at: '', updated_at: '',
    }])
    const wrapper = mount(AnnotationWorkbenchView, {
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

    expect(wrapper.get('[data-test="run-batch-auto"]').attributes('disabled')).toBeDefined()
    expect(mocks.createBatchAutoAnnotation).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
