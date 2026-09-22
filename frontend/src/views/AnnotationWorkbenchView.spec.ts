import { flushPromises, mount } from '@vue/test-utils'
import { Aim, Mouse, PriceTag } from '@element-plus/icons-vue'
import { ElNotification } from 'element-plus'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AnnotationWorkbenchView from './AnnotationWorkbenchView.vue'
import AutoAnnotationCategorySelect from '../components/AutoAnnotationCategorySelect.vue'

const mocks = vi.hoisted(() => ({
  routeLeaveGuard: vi.fn(),
  routerBack: vi.fn(),
  routerReplace: vi.fn(),
  getProject: vi.fn(),
  listVideos: vi.fn(),
  listLabels: vi.fn(),
  createLabel: vi.fn(),
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
  listLLMConfigs: vi.fn(),
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
  onBeforeRouteLeave: mocks.routeLeaveGuard,
  useRoute: () => ({ params: { id: 'project-id', videoId: 'video-id' } }),
  useRouter: () => ({ back: mocks.routerBack, replace: mocks.routerReplace }),
}))
vi.mock('../api/projects', () => ({ getProject: mocks.getProject }))
vi.mock('../api/auth', () => ({ getCurrentUser: mocks.getCurrentUser }))
vi.mock('../api/capabilities', () => ({ getCapabilities: mocks.getCapabilities }))
vi.mock('../api/labels', () => ({
  listLabels: mocks.listLabels,
  createLabel: mocks.createLabel,
}))
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
vi.mock('../api/llm', () => ({ listLLMConfigs: mocks.listLLMConfigs }))
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
  props: ['dragToDraw'],
  emits: ['change', 'request-category', 'view-change'],
  template: '<div data-test="canvas-stub" :data-drag-to-draw="String(dragToDraw)"><button data-test="canvas-change" @click="$emit(\'change\', [{ id: \'box-id\', label_id: \'label-id\', x_min: 1, y_min: 2, x_max: 30, y_max: 40, source: \'manual\', confidence: null }])">change</button><button data-test="request-category" @click="$emit(\'request-category\', { x_min: 10, y_min: 20, x_max: 110, y_max: 220 }, { x: 50, y: 60 })">draw</button><button data-test="request-category-lower-right" @click="$emit(\'request-category\', { x_min: 10, y_min: 20, x_max: 110, y_max: 220 }, { x: 1200, y: 900 })">draw lower right</button><button data-test="view-change" @click="$emit(\'view-change\', { x_min: 100, y_min: 200, x_max: 900, y_max: 700 })">view</button></div>',
})
const SelectStub = defineComponent({
  props: ['filterMethod'],
  template: '<div><button data-test="filter-person" @click="filterMethod?.(\'person\')">person</button><slot /></div>',
})
const NativeSelectStub = defineComponent({
  inheritAttrs: false,
  props: ['modelValue'],
  emits: ['update:modelValue', 'change'],
  template: `<select v-bind="$attrs" :value="modelValue" @change="$emit('update:modelValue', $event.target.value); $emit('change', $event.target.value)"><slot /></select>`,
})
const NativeOptionStub = defineComponent({
  props: ['value', 'label'],
  template: '<option :value="value">{{ label }}</option>',
})

const project = {
  id: 'project-id',
  name: '安全帽',
  description: '',
  creator_id: 'creator-id',
  creator_username: 'creator',
  access: {
    role: 'editor', source: 'membership',
    permissions: ['project.read', 'project.update', 'artifact.read', 'artifact.download', 'artifact.consume', 'task.read', 'task.execute'],
  },
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
const modelProject = {
  id: 'model-project-id',
  name: '可操作模型项目',
  description: '',
  series_type: 'archive' as const,
  system_key: null,
  created_by_id: 'editor-id',
  version: 1,
  can_manage: true,
  access: {
    role: 'owner' as const,
    source: 'owner' as const,
    permissions: ['project.read', 'project.update', 'artifact.read', 'artifact.download', 'artifact.consume', 'task.read', 'task.execute'],
  },
  created_at: '',
  updated_at: '',
  tags: [],
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
  window.history.replaceState({ annotationFromVideoList: true }, '')
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
  mocks.listModelProjects.mockResolvedValue([modelProject])
  mocks.listModelProjectModels.mockImplementation(() => mocks.listInferenceModels())
  mocks.getXAnyLabelingSetting.mockResolvedValue({
    configured: false,
    server_url: '',
    has_api_key: false,
    available: null,
  })
  mocks.listXAnyLabelingModels.mockResolvedValue([])
  mocks.listLLMConfigs.mockResolvedValue([])
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

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('AnnotationWorkbenchView', () => {
  it('keeps only frame enablement at the top and uses icon toggles in the tool rail', async () => {
    const wrapper = mount(AnnotationWorkbenchView, {
      global: {
        stubs: {
          AnnotationCanvas: CanvasStub,
          ElSwitch: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.get('.frame-controls').find('[data-test="frame-enabled-switch"]').exists()).toBe(true)
    expect(wrapper.find('.tool-switches').exists()).toBe(false)
    expect(wrapper.get('[data-test="drag-to-draw-toggle"]').attributes('aria-pressed')).toBe('false')
    expect(wrapper.get('[data-test="reuse-label-toggle"]').attributes('aria-pressed')).toBe('false')
    expect(wrapper.get('[data-test="crosshair-toggle"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.findComponent(Mouse).exists()).toBe(true)
    expect(wrapper.findComponent(PriceTag).exists()).toBe(true)
    expect(wrapper.findComponent(Aim).exists()).toBe(true)
    expect(wrapper.get('[data-test="canvas-stub"]').attributes('data-drag-to-draw')).toBe('false')

    await wrapper.get('[data-test="drag-to-draw-toggle"]').trigger('click')

    expect(wrapper.get('[data-test="drag-to-draw-toggle"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-test="canvas-stub"]').attributes('data-drag-to-draw')).toBe('true')
    wrapper.unmount()
  })

  it('does not offer read-only built-in projects as auto-annotation sources', async () => {
    mocks.listModelProjects.mockResolvedValueOnce([{
      ...modelProject,
      id: 'official-project-id',
      name: 'YOLO11目标检测官方模型',
      system_key: 'official_yolo11',
      can_manage: false,
      access: {
        role: 'viewer',
        source: 'system_resource',
        permissions: ['project.read', 'artifact.read', 'artifact.download', 'task.read'],
      },
    }])
    const wrapper = mount(AnnotationWorkbenchView, {
      global: { stubs: { AnnotationCanvas: CanvasStub } },
    })
    await flushPromises()

    expect(mocks.listModelProjectModels).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('YOLO11目标检测官方模型')
    wrapper.unmount()
  })

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
    expect(wrapper.get('[data-test="crosshair-toggle"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('.image-info dl').exists()).toBe(true)
    expect(wrapper.get('.image-info dl dd').text()).toBe('TESTV001_frame_000001.jpg')
    expect(wrapper.get('.minimap-svg').attributes('viewBox')).toBe('0 0 1920 1080')
    await wrapper.get('[data-test="view-change"]').trigger('click')
    expect(wrapper.get('.viewport-box').attributes()).toMatchObject({
      x: '100', y: '200', width: '800', height: '500',
    })
    expect(wrapper.get('[data-test="toggle-all-boxes"]').attributes('title')).toBe('隐藏全部标注框')
    expect(wrapper.get('[data-test="image-info-toggle"]').attributes('aria-expanded')).toBe('true')
    await wrapper.get('[data-test="image-info-toggle"]').trigger('click')
    expect(wrapper.get('[data-test="image-info-toggle"]').attributes('aria-expanded')).toBe('false')
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
    expect(mocks.routerBack).toHaveBeenCalledOnce()
    expect(mocks.routerReplace).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('falls back to the video list after direct entry and saves before route leave', async () => {
    window.history.replaceState({}, '')
    const wrapper = mount(AnnotationWorkbenchView, {
      attachTo: document.body,
      global: { stubs: { AnnotationCanvas: CanvasStub } },
    })
    await flushPromises()

    document.querySelector<HTMLElement>('[data-test="close-annotation"]')?.click()
    await flushPromises()
    expect(mocks.routerBack).not.toHaveBeenCalled()
    expect(mocks.routerReplace).toHaveBeenCalledWith('/projects/project-id/videos')

    await wrapper.get('[data-test="canvas-change"]').trigger('click')
    const guard = mocks.routeLeaveGuard.mock.calls[0][0]
    expect(await guard()).toBe(true)
    expect(mocks.replaceFrameAnnotations).toHaveBeenCalledOnce()

    await wrapper.get('[data-test="canvas-change"]').trigger('click')
    mocks.replaceFrameAnnotations.mockRejectedValueOnce(new Error('保存失败'))
    expect(await guard()).toBe(false)
    wrapper.unmount()
  })

  it('redirects viewers instead of opening annotation controls', async () => {
    mocks.getProject.mockResolvedValueOnce({
      ...project,
      access: {
        role: 'viewer', source: 'membership',
        permissions: ['project.read', 'artifact.read', 'artifact.download', 'task.read'],
      },
    })
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
    vi.spyOn(wrapper.get('.canvas-panel').element, 'getBoundingClientRect').mockReturnValue({
      left: 100,
      top: 200,
    } as DOMRect)

    expect(wrapper.findAll('[data-test="stats-row"]').map((row) => row.text())).toEqual([
      '采样帧2',
      '启用帧2',
      '当前帧标注框0',
      '所有帧标注框0',
    ])
    expect(
      wrapper.get('[data-test="shortcut-list"]').findAll('dt').map((item) => item.text()),
    ).toEqual(expect.arrayContaining(['S', 'Y', 'L', 'H', 'P']))
    expect(wrapper.get('[data-test="shortcut-list"]').text()).toContain('拖动四角自由调整标注框宽高')
    expect(wrapper.get('[data-test="shortcut-list"]').text()).toContain('Shift + 拖动四角等比例缩放标注框')
    expect(wrapper.get('[data-test="shortcut-list"]').text()).toContain('Alt + 拖动四角以中心为基准向四周缩放')
    await wrapper.get('[data-test="request-category"]').trigger('click')
    expect(wrapper.find('[data-test="category-scrim"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="category-picker"]').attributes('style')).toContain('left: 150px')
    expect(wrapper.get('[data-test="category-picker"]').attributes('style')).toContain('top: 260px')
    expect(wrapper.get('[data-test="category-picker"]').classes()).not.toContain('opens-left')
    expect(wrapper.get('[data-test="category-picker"]').classes()).not.toContain('opens-up')
    await wrapper.get('[data-test="add-category-toggle"]').trigger('click')
    expect(wrapper.find('[data-test="category-create-form"]').exists()).toBe(true)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[data-test="category-create-form"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="category-picker"]').exists()).toBe(true)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[data-test="category-picker"]').exists()).toBe(false)

    await wrapper.get('[data-test="request-category-lower-right"]').trigger('click')
    expect(wrapper.get('[data-test="category-picker"]').attributes('style')).toContain(`left: ${window.innerWidth - 12}px`)
    expect(wrapper.get('[data-test="category-picker"]').attributes('style')).toContain(`top: ${window.innerHeight - 12}px`)
    expect(wrapper.get('[data-test="category-picker"]').classes()).toContain('opens-left')
    expect(wrapper.get('[data-test="category-picker"]').classes()).toContain('opens-up')
    await wrapper.get('[data-test="cancel-category"]').trigger('click')

    await wrapper.get('[data-test="request-category"]').trigger('click')
    await wrapper.get('[data-test="confirm-category"]').trigger('click')
    await wrapper.get('[data-test="next-frame"]').trigger('click')
    await flushPromises()
    expect(mocks.replaceFrameAnnotations.mock.calls[0]?.[2].items).toHaveLength(1)
    wrapper.unmount()
  })

  it('creates a label from the picker and applies it to the pending rectangle', async () => {
    mocks.createLabel.mockResolvedValue({
      id: 'safety-vest-id',
      name: 'safety_vest',
      description_zh: '',
      color: '#d94f91',
      sort_order: 1,
      enabled: true,
      version: 1,
      created_at: '',
      updated_at: '',
    })
    const wrapper = mount(AnnotationWorkbenchView, {
      attachTo: document.body,
      global: { stubs: { AnnotationCanvas: CanvasStub, ElSwitch: true } },
    })
    await flushPromises()

    await wrapper.get('[data-test="request-category"]').trigger('click')
    await wrapper.get('[data-test="add-category-toggle"]').trigger('click')
    const input = wrapper.get('[data-test="new-category-name"]')
    const preview = wrapper.get('[data-test="category-color-preview"]')
    expect(document.activeElement).toBe(input.element)
    expect(preview.attributes('aria-label')).toMatch(/^自动颜色 #[0-9a-f]{6}$/)

    await input.setValue(' Safety_Vest ')
    await wrapper.get('[data-test="category-create-form"]').trigger('submit')
    await flushPromises()

    expect(mocks.createLabel).toHaveBeenCalledWith(
      'project-id',
      'safety_vest',
      '',
      expect.stringMatching(/^#[0-9a-f]{6}$/),
    )
    expect(wrapper.find('[data-test="category-picker"]').exists()).toBe(false)
    await wrapper.get('[data-test="next-frame"]').trigger('click')
    await flushPromises()
    expect(mocks.replaceFrameAnnotations.mock.calls[0]?.[2].items[0].label_id).toBe('safety-vest-id')
    wrapper.unmount()
  })

  it('reuses an enabled label and rejects invalid or disabled names locally', async () => {
    mocks.listLabels.mockResolvedValueOnce([
      { id: 'label-id', name: 'helmet', description_zh: '安全帽', color: '#16866f', sort_order: 0, enabled: true, version: 1, created_at: '', updated_at: '' },
      { id: 'archived-id', name: 'archived', description_zh: '', color: '#e85d4a', sort_order: 1, enabled: false, version: 1, created_at: '', updated_at: '' },
    ])
    const wrapper = mount(AnnotationWorkbenchView, {
      global: { stubs: { AnnotationCanvas: CanvasStub, ElSwitch: true } },
    })
    await flushPromises()

    await wrapper.get('[data-test="request-category"]').trigger('click')
    await wrapper.get('[data-test="add-category-toggle"]').trigger('click')
    const input = wrapper.get('[data-test="new-category-name"]')
    await input.setValue('helmet@person')
    await wrapper.get('[data-test="category-create-form"]').trigger('submit')
    expect(wrapper.get('[data-test="category-create-error"]').text()).toContain('小写字母')
    expect(mocks.createLabel).not.toHaveBeenCalled()

    await input.setValue(' archived ')
    await wrapper.get('[data-test="category-create-form"]').trigger('submit')
    expect(wrapper.get('[data-test="category-create-error"]').text()).toContain('已停用')
    expect(mocks.createLabel).not.toHaveBeenCalled()

    await input.setValue(' HELMET ')
    await wrapper.get('[data-test="category-create-form"]').trigger('submit')
    expect(wrapper.find('[data-test="category-picker"]').exists()).toBe(false)
    expect(mocks.createLabel).not.toHaveBeenCalled()
    await wrapper.get('[data-test="next-frame"]').trigger('click')
    await flushPromises()
    expect(mocks.replaceFrameAnnotations.mock.calls[0]?.[2].items[0].label_id).toBe('label-id')
    wrapper.unmount()
  })

  it('keeps quick-create state after an API failure and allows retry', async () => {
    const created = {
      id: 'dog-id', name: 'dog', description_zh: '', color: '#2f80ed', sort_order: 1,
      enabled: true, version: 1, created_at: '', updated_at: '',
    }
    mocks.createLabel
      .mockRejectedValueOnce(new Error('标签添加失败'))
      .mockResolvedValueOnce(created)
    const wrapper = mount(AnnotationWorkbenchView, {
      global: { stubs: { AnnotationCanvas: CanvasStub, ElSwitch: true } },
    })
    await flushPromises()

    await wrapper.get('[data-test="request-category"]').trigger('click')
    await wrapper.get('[data-test="add-category-toggle"]').trigger('click')
    const input = wrapper.get('[data-test="new-category-name"]')
    const colorLabel = wrapper.get('[data-test="category-color-preview"]').attributes('aria-label')
    await input.setValue('dog')
    await wrapper.get('[data-test="category-create-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-test="category-create-error"]').text()).toBe('标签添加失败')
    expect(wrapper.get('[data-test="new-category-name"]').element).toHaveProperty('value', 'dog')
    expect(wrapper.get('[data-test="category-color-preview"]').attributes('aria-label')).toBe(colorLabel)
    expect(wrapper.find('[data-test="category-picker"]').exists()).toBe(true)

    await wrapper.get('[data-test="category-create-form"]').trigger('submit')
    await flushPromises()
    expect(mocks.createLabel).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="category-picker"]').exists()).toBe(false)
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
    expect(panTool.attributes('aria-pressed')).toBe('false')
    await panTool.trigger('click')
    expect(panTool.classes()).toContain('active')
    expect(panTool.attributes('aria-pressed')).toBe('true')
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
    expect(wrapper.get('[data-test="reuse-label-toggle"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-test="crosshair-toggle"]').attributes('aria-pressed')).toBe('false')
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

  it('submits a typed category with the configured X-AnyLabeling model', async () => {
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
          ElSelect: SelectStub,
          ElOption: true,
          ElInputNumber: true,
          ElSwitch: true,
          ElDialog: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('[data-test="auto-categories"] [data-test="filter-person"]').trigger('click')
    await wrapper.get('[data-test="run-single-auto"]').trigger('click')
    await flushPromises()

    expect(mocks.runFrameAutoAnnotation.mock.calls[0]?.[3]).toMatchObject({
      source: 'xanylabeling', model_id: 'remote', remote_task_id: 'grounding',
      categories: ['person'],
    })
    wrapper.unmount()
  })

  it('expands All to enabled project labels for an X-AnyLabeling text-prompt model', async () => {
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
      source: 'xanylabeling',
      categories: ['helmet'],
    })
    wrapper.unmount()
  })

  it('keeps All unfiltered for default X-AnyLabeling models', async () => {
    mocks.listModelProjects.mockResolvedValueOnce([])
    mocks.getXAnyLabelingSetting.mockResolvedValueOnce({
      configured: true,
      server_url: 'http://127.0.0.1:44444',
      has_api_key: false,
      available: true,
    })
    mocks.listXAnyLabelingModels.mockResolvedValueOnce([{
      key: '["remote",null]',
      model_id: 'remote',
      task_id: null,
      name: 'Remote',
      batch_processing_mode: 'default',
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

    expect(mocks.runFrameAutoAnnotation.mock.calls[0]?.[3].categories).toEqual([])
    wrapper.unmount()
  })

  it('blocks an empty All prompt for an X-AnyLabeling text-prompt model', async () => {
    const warning = vi.spyOn(ElNotification, 'warning').mockReturnValue({ close: vi.fn() } as never)
    mocks.listLabels.mockResolvedValueOnce([])
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

    expect(mocks.runFrameAutoAnnotation).not.toHaveBeenCalled()
    expect(warning).toHaveBeenCalledWith(expect.objectContaining({
      message: '当前 X-AnyLabeling 模型需要类别提示词，请先新增、启用或手动输入类别。',
    }))
    wrapper.unmount()
  })

  it('submits the selected online configuration id for a single run', async () => {
    mocks.listLLMConfigs.mockResolvedValueOnce([{
      id: 'llm-id', name: 'Online Vision', description: '',
      base_url: 'https://model.test/v1', api_type: 'openai', model_name: 'vision-model',
      has_api_key: true, masked_api_key: '********', enabled: true, available: true,
      last_test_status: 'success', last_test_latency_ms: 20, advanced_options: {}, version: 1,
      created_at: '', updated_at: '',
    }])
    mocks.runFrameAutoAnnotation.mockResolvedValue({ items: [], created_labels: [] })
    const wrapper = mount(AnnotationWorkbenchView, {
      global: {
        stubs: {
          AnnotationCanvas: CanvasStub,
          ElSelect: NativeSelectStub,
          ElOption: NativeOptionStub,
          ElInputNumber: true,
          ElSwitch: true,
          ElDialog: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('[data-test="model-project-select"]').setValue('online')
    await flushPromises()
    expect(wrapper.get('[data-test="inference-model-select"]').element).toHaveProperty('value', 'llm-id')
    await wrapper.get('[data-test="run-single-auto"]').trigger('click')
    await flushPromises()

    expect(mocks.runFrameAutoAnnotation).toHaveBeenCalledWith(
      'project-id',
      'video-id',
      'frame-1',
      expect.objectContaining({ source: 'online', model_id: 'llm-id', remote_task_id: null }),
    )
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

    wrapper.getComponent(AutoAnnotationCategorySelect).vm.$emit('update:modelValue', ['helmet'])
    await wrapper.get('[data-test="run-single-auto"]').trigger('click')
    await flushPromises()
    expect(mocks.runFrameAutoAnnotation.mock.calls[0]?.[3].categories).toEqual(['helmet'])

    wrapper.getComponent(AutoAnnotationCategorySelect).vm.$emit('update:modelValue', ['__all__'])
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
