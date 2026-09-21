import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import HyperparameterTemplateDetailView from './HyperparameterTemplateDetailView.vue'

const mocks = vi.hoisted(() => ({
  getTemplate: vi.fn(),
  getProject: vi.fn(),
  listMembers: vi.fn(),
}))

vi.mock('vue-router', () => ({
  RouterLink: { props: ['to'], template: '<a><slot /></a>' },
  useRoute: () => ({ params: { id: 'template-id' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('../api/hyperparameters', () => ({
  getHyperparameterTemplate: mocks.getTemplate,
}))
vi.mock('../api/models', () => ({
  getModelProject: mocks.getProject,
  listModelProjectMembers: mocks.listMembers,
  addModelProjectMember: vi.fn(),
  changeModelProjectMemberRole: vi.fn(),
  removeModelProjectMember: vi.fn(),
}))

const template = {
  id: 'template-id', model_project_id: 'project-id', name: '训练模板', description: '',
  epochs: 100, batch_mode: 'auto', batch_value: null, image_size: 640,
  extra_parameters: {}, effective_parameters: {}, catalog_version: '1',
  system_key: null, derived_from_id: null, created_by_id: 'owner-id',
  can_manage: true, can_edit: true, version: 1,
  created_at: '2026-09-21T00:00:00Z', updated_at: '2026-09-21T00:00:00Z',
}
const project = {
  id: 'project-id', name: '模板来源项目', description: '', series_type: 'archive',
  system_key: null, created_by_id: 'owner-id', version: 1, can_manage: true,
  access: {
    role: 'owner', source: 'owner',
    permissions: ['project.read', 'project.update', 'project.members.manage'],
  },
  created_at: '', updated_at: '', tags: [],
}

describe('HyperparameterTemplateDetailView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getTemplate.mockResolvedValue(template)
    mocks.getProject.mockResolvedValue(project)
    mocks.listMembers.mockResolvedValue([])
  })

  it('shows the owning model project and its shared member panel', async () => {
    const wrapper = mount(HyperparameterTemplateDetailView, {
      global: {
        plugins: [ElementPlus],
        stubs: { RouterLink: { template: '<a><slot /></a>' } },
      },
    })
    await flushPromises()

    expect(mocks.getProject).toHaveBeenCalledWith('project-id')
    expect(wrapper.text()).toContain('模板来源项目')
    expect(wrapper.text()).toContain('成员授权作用于模板所属的整个模型项目')
  })

  it('explains that system templates cannot be authorized separately', async () => {
    mocks.getTemplate.mockResolvedValue({
      ...template,
      model_project_id: null,
      system_key: 'ultralytics-detect-default',
    })
    const wrapper = mount(HyperparameterTemplateDetailView, {
      global: {
        plugins: [ElementPlus],
        stubs: { RouterLink: { template: '<a><slot /></a>' } },
      },
    })
    await flushPromises()

    expect(mocks.getProject).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('所有正常账号均可读取，不支持单独授权')
  })
})
