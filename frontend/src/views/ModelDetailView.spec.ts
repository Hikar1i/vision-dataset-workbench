import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, expect, it, vi } from 'vitest'

import ModelDetailView from './ModelDetailView.vue'

const mocks = vi.hoisted(() => ({
  getModel: vi.fn(),
  listProjects: vi.fn(),
  listArtifacts: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: 'project-id', modelId: 'model-id' } }) }))
vi.mock('../api/models', () => ({
  getInferenceModel: mocks.getModel,
  listModelProjects: mocks.listProjects,
  modelDownloadUrl: (id: string) => `/models/${id}/download`,
  updateInferenceModel: vi.fn(),
}))
vi.mock('../api/modelArtifacts', () => ({
  listModelArtifacts: mocks.listArtifacts,
  modelArtifactDownloadUrl: (id: string) => `/artifacts/${id}/download`,
}))

beforeEach(() => {
  mocks.getModel.mockResolvedValue({
    id: 'model-id',
    model_project_id: 'project-id',
    model_code: 'helmet-v1',
    name: 'Helmet detector',
    description: '',
    parameters: {},
    kind: 'yolo',
    status: 'ready',
    storage_path: 'models/model-id/model.pt',
    file_size: 1024,
    sha256: 'a'.repeat(64),
    source_name: 'model.pt',
    error: null,
    version: 1,
    can_manage: true,
    can_convert: true,
    access: {
      role: 'owner', source: 'owner',
      permissions: ['project.read', 'project.update', 'project.members.manage', 'project.delete', 'artifact.read', 'artifact.download', 'artifact.consume', 'task.read', 'task.execute'],
    },
    created_at: '2026-09-17T08:00:00Z',
    updated_at: '2026-09-17T08:00:00Z',
    training: null,
  })
  mocks.listProjects.mockResolvedValue([])
  mocks.listArtifacts.mockResolvedValue([
    {
      id: 'onnx-id',
      model_id: 'model-id',
      format: 'onnx',
      status: 'ready',
      export_config: { imgsz: 640, dynamic: true, precision: null },
      file_size: 2048,
    },
  ])
})

it('shows the source download split and reusable conversion artifact', async () => {
  const wrapper = mount(ModelDetailView, {
    global: {
      plugins: [ElementPlus],
      stubs: {
        PageHeader: { template: '<div><slot name="actions" /><slot /></div>' },
        ModelArtifactDialog: true,
      },
    },
  })
  await flushPromises()

  expect(wrapper.text()).toContain('下载 .pt')
  expect(wrapper.text()).toContain('格式转换')
  expect(wrapper.text()).toContain('ONNX')
  expect(wrapper.find('a[href="/artifacts/onnx-id/download"]').exists()).toBe(true)
})
