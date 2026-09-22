import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import BatchAnnotationDialog from './BatchAnnotationDialog.vue'
import AutoAnnotationCategorySelect from './AutoAnnotationCategorySelect.vue'
import XAnyLabelingSettingsDialog from './XAnyLabelingSettingsDialog.vue'

const mocks = vi.hoisted(() => ({
  listProjects: vi.fn(), listModels: vi.fn(), listRemote: vi.fn(), getSetting: vi.fn(),
  listLLM: vi.fn(), create: vi.fn(),
  listLabels: vi.fn(),
}))
vi.mock('../api/models', () => ({
  listModelProjects: mocks.listProjects,
  listModelProjectModels: mocks.listModels,
  listXAnyLabelingModels: mocks.listRemote,
  getXAnyLabelingSetting: mocks.getSetting,
  createProjectBatchAutoAnnotation: mocks.create,
}))
vi.mock('../api/llm', () => ({ listLLMConfigs: mocks.listLLM }))
vi.mock('../api/labels', () => ({ listLabels: mocks.listLabels }))

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
  mocks.listModels.mockResolvedValue([{ id: 'model-id', name: 'YOLO11n', status: 'ready' }])
  mocks.listRemote.mockResolvedValue([])
  mocks.getSetting.mockResolvedValue({
    configured: false, server_url: '', has_api_key: false, available: null,
  })
  mocks.listLLM.mockResolvedValue([{ id: 'llm-id', name: '视觉模型', enabled: true, available: true }])
  mocks.listLabels.mockResolvedValue([
    { id: 'person', name: 'person', enabled: true },
    { id: 'disabled', name: 'disabled', enabled: false },
  ])
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
    expect(wrapper.get('[data-test="annotation-risk-confirm"] input').attributes('aria-label'))
      .toBe('确认对已有标注的视频执行自动标注')
    expect(wrapper.get('[data-test="annotation-create-task"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="annotation-create-task"]').attributes('title'))
      .toBe('请先确认已标注视频处理风险')
    await wrapper.get('[data-test="annotation-risk-confirm"] input').setValue(true)
    await flushPromises()
    expect(wrapper.get('[data-test="annotation-create-task"]').attributes('disabled')).toBeUndefined()
  })

  it('uses the unified source order and submits selected plus typed categories', async () => {
    const wrapper = mountDialog('unannotated')
    await flushPromises()

    const source = wrapper.getComponent({ name: 'ElSelect' })
    expect(source.findAllComponents({ name: 'ElOption' }).map((item) => item.props('value')))
      .toEqual(['xanylabeling', 'online', 'project:project-models'])
    expect(source.findAllComponents({ name: 'ElOption' })[0]?.props('label'))
      .toBe('X-anylabeling-server')

    source.vm.$emit('change', 'online')
    await flushPromises()
    expect(mocks.listLLM).toHaveBeenCalled()
    const categorySelect = wrapper.getComponent(AutoAnnotationCategorySelect)
    categorySelect.vm.$emit('update:modelValue', ['person'])
    categorySelect.vm.$emit('update:query', 'Helmet')
    await flushPromises()
    await wrapper.get('[data-test="annotation-create-task"]').trigger('click')
    await flushPromises()

    expect(mocks.create).toHaveBeenCalledWith(
      'project-id',
      ['video-new'],
      expect.objectContaining({
        source: 'online', model_id: 'llm-id', remote_task_id: null,
        categories: ['person', 'helmet'],
      }),
      'unannotated',
      false,
    )
  })

  it('keeps typed category entry available when project labels fail to load', async () => {
    mocks.listLabels.mockRejectedValueOnce(new Error('offline'))
    const wrapper = mountDialog('unannotated')
    await flushPromises()

    expect(wrapper.text()).toContain('类别列表加载失败，可继续输入新类别。')
    expect(wrapper.getComponent(AutoAnnotationCategorySelect).props('labels')).toEqual([])
    expect(wrapper.getComponent(AutoAnnotationCategorySelect).props('disabled')).toBe(false)
  })

  it('expands All to enabled project labels for X-AnyLabeling text-prompt tasks', async () => {
    const wrapper = mountDialog('unannotated')
    await flushPromises()
    wrapper.getComponent(XAnyLabelingSettingsDialog).vm.$emit('saved', {
      configured: true,
      server_url: 'http://127.0.0.1:44444',
      has_api_key: false,
      available: true,
    }, [{
      key: '["remote","grounding"]',
      model_id: 'remote',
      task_id: 'grounding',
      name: 'Remote / Grounding',
      batch_processing_mode: 'text_prompt',
    }])
    await flushPromises()

    await wrapper.get('[data-test="annotation-create-task"]').trigger('click')
    await flushPromises()

    expect(mocks.create).toHaveBeenCalledWith(
      'project-id',
      ['video-new'],
      expect.objectContaining({
        source: 'xanylabeling',
        categories: ['person'],
      }),
      'unannotated',
      false,
    )
  })

  it('blocks an empty All prompt for X-AnyLabeling text-prompt tasks', async () => {
    mocks.listLabels.mockResolvedValueOnce([
      { id: 'disabled', name: 'disabled', enabled: false },
    ])
    const wrapper = mountDialog('unannotated')
    await flushPromises()
    wrapper.getComponent(XAnyLabelingSettingsDialog).vm.$emit('saved', {
      configured: true,
      server_url: 'http://127.0.0.1:44444',
      has_api_key: false,
      available: true,
    }, [{
      key: '["remote","grounding"]',
      model_id: 'remote',
      task_id: 'grounding',
      name: 'Remote / Grounding',
      batch_processing_mode: 'text_prompt',
    }])
    await flushPromises()

    await wrapper.get('[data-test="annotation-create-task"]').trigger('click')
    await flushPromises()

    expect(mocks.create).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(
      '当前 X-AnyLabeling 模型需要类别提示词，请先新增、启用或手动输入类别。',
    )
  })
})
