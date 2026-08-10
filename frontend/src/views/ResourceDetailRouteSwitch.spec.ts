import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ModelProjectDetailView from './ModelProjectDetailView.vue'
import TrainingTaskDetailView from './TrainingTaskDetailView.vue'

const mocks = vi.hoisted(() => ({
  getModelProject: vi.fn(),
  listModelProjectModels: vi.fn().mockResolvedValue([]),
  listModelProjectTags: vi.fn().mockResolvedValue([]),
  getTrainingTask: vi.fn(),
}))

vi.mock('../api/models', () => ({
  deleteInferenceModel: vi.fn(),
  getModelProject: mocks.getModelProject,
  listModelProjectModels: mocks.listModelProjectModels,
  listModelProjectTags: mocks.listModelProjectTags,
  modelDownloadUrl: (id: string) => `/api/v1/models/${id}/download`,
  registerInferenceModel: vi.fn(),
  updateModelProject: vi.fn(),
}))

vi.mock('../api/training', () => ({
  cancelTrainingModel: vi.fn(),
  cancelTrainingTask: vi.fn(),
  deleteTrainingModel: vi.fn(),
  deleteTrainingTask: vi.fn(),
  deriveTrainingTask: vi.fn(),
  getTrainingTask: mocks.getTrainingTask,
  retryFailedTrainingModels: vi.fn(),
  retryTrainingModel: vi.fn(),
  resumeInterruptedTrainingModels: vi.fn(),
  resumeTrainingModel: vi.fn(),
  startTrainingTask: vi.fn(),
}))

function modelProject(id: string) {
  return {
    id,
    name: `模型项目 ${id}`,
    description: '',
    series_type: 'archive',
    system_key: null,
    created_by_id: 'user-1',
    version: 1,
    can_manage: true,
    created_at: '2026-08-05T00:00:00Z',
    updated_at: '2026-08-05T00:00:00Z',
    tags: ['测试'],
  }
}

function trainingTask(id: string) {
  return {
    id,
    code: `task-${id.toLowerCase()}`,
    name: `训练任务 ${id}`,
    description: '',
    status: 'draft',
    mode: 'single_model',
    progress: 0,
    model_count: 0,
    default_dataset_export_id: null,
    default_template_id: null,
    default_base_model_id: null,
    created_by_id: 'user-1',
    can_manage: true,
    version: 1,
    submitted_at: null,
    last_run_at: null,
    started_at: null,
    finished_at: null,
    created_at: '2026-08-05T00:00:00Z',
    updated_at: '2026-08-05T00:00:00Z',
    actions: {},
    models: [],
  }
}

async function mountDetail(component: object, path: string, initial: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path, component }],
  })
  await router.push(initial)
  await router.isReady()
  const wrapper = mount({ template: '<RouterView />' }, {
    global: { plugins: [router, ElementPlus] },
  })
  await flushPromises()
  return { router, wrapper }
}

describe('resource detail route switching', () => {
  beforeEach(() => {
    localStorage.clear()
    mocks.getModelProject.mockImplementation(async (id: string) => modelProject(id))
    mocks.getTrainingTask.mockImplementation(async (id: string) => trainingTask(id))
  })

  it('loads the model project selected by the new route id', async () => {
    const { router, wrapper } = await mountDetail(
      ModelProjectDetailView,
      '/model-projects/:id',
      '/model-projects/A',
    )

    await router.push('/model-projects/B')
    await flushPromises()

    expect(mocks.getModelProject).toHaveBeenLastCalledWith('B')
    expect(wrapper.get('h1').text()).toBe('模型项目 B')
    wrapper.unmount()
  })

  it('does not let a slower model-project response replace the current route', async () => {
    let resolveA!: (value: ReturnType<typeof modelProject>) => void
    mocks.getModelProject.mockImplementation((id: string) => id === 'A'
      ? new Promise((resolve) => { resolveA = resolve })
      : Promise.resolve(modelProject(id)))
    const { router, wrapper } = await mountDetail(
      ModelProjectDetailView,
      '/model-projects/:id',
      '/model-projects/A',
    )

    await router.push('/model-projects/B')
    await flushPromises()
    resolveA(modelProject('A'))
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('模型项目 B')
    wrapper.unmount()
  })

  it('loads the training task selected by the new route id', async () => {
    const { router, wrapper } = await mountDetail(
      TrainingTaskDetailView,
      '/training-tasks/:id',
      '/training-tasks/A',
    )

    await router.push('/training-tasks/B')
    await flushPromises()

    expect(mocks.getTrainingTask).toHaveBeenLastCalledWith('B')
    expect(wrapper.get('h1').text()).toBe('训练任务 B')
    wrapper.unmount()
  })
})
