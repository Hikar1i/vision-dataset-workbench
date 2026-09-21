import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ModelProjectDetailView from './ModelProjectDetailView.vue'

const mocks = vi.hoisted(() => ({
  getProject: vi.fn(),
  listModels: vi.fn(),
  listTags: vi.fn(),
  listMembers: vi.fn(),
  addMember: vi.fn(),
  changeRole: vi.fn(),
  removeMember: vi.fn(),
}))

vi.mock('vue-router', () => ({
  RouterLink: { props: ['to'], template: '<a><slot /></a>' },
  useRoute: () => ({ params: { id: 'project-id' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('../api/models', () => ({
  getModelProject: mocks.getProject,
  listModelProjectModels: mocks.listModels,
  listModelProjectTags: mocks.listTags,
  listModelProjectMembers: mocks.listMembers,
  addModelProjectMember: mocks.addMember,
  changeModelProjectMemberRole: mocks.changeRole,
  removeModelProjectMember: mocks.removeMember,
  deleteInferenceModel: vi.fn(),
  modelDownloadUrl: vi.fn(),
  registerInferenceModel: vi.fn(),
  updateModelProject: vi.fn(),
}))
vi.mock('../api/modelArtifacts', () => ({
  listModelArtifacts: vi.fn().mockResolvedValue([]),
  modelArtifactDownloadUrl: vi.fn(),
}))

const owner = { id: 'owner-id', username: 'owner', status: 'active', role: 'owner', created_at: '' }
const editor = { id: 'editor-id', username: 'editor', status: 'active', role: 'editor', created_at: '' }
const project = {
  id: 'project-id', name: '模型项目', description: '', series_type: 'archive',
  system_key: null, created_by_id: 'owner-id', version: 1, can_manage: true,
  access: {
    role: 'owner', source: 'owner',
    permissions: ['project.read', 'project.update', 'project.members.manage', 'project.delete', 'artifact.read', 'artifact.download', 'artifact.consume', 'task.read', 'task.execute'],
  },
  created_at: '2026-09-20T00:00:00Z', updated_at: '2026-09-20T00:00:00Z', tags: ['检测'],
}

const source = readFileSync(resolve('src/views/ModelProjectDetailView.vue'), 'utf8')

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getProject.mockResolvedValue(project)
  mocks.listModels.mockResolvedValue([])
  mocks.listTags.mockResolvedValue([])
  mocks.listMembers.mockResolvedValue([owner, editor])
  mocks.addMember.mockResolvedValue({ ...editor, id: 'viewer-id', username: 'viewer', role: 'viewer' })
  mocks.changeRole.mockResolvedValue({ ...editor, role: 'viewer' })
  mocks.removeMember.mockResolvedValue(undefined)
})

describe('ModelProjectDetailView', () => {
  it('keeps subpage actions in the body and exposes the compact model action set', () => {
    expect(source).not.toContain("'添加时间'")
    expect(source).toContain('model-list-toolbar')
    expect(source).toContain('evaluation_peak')
    expect(source).toContain('下载 PyTorch 模型')
    expect(source).toContain('在线推理')
    expect(source).toContain('在线评估')
    expect(source).toContain('格式转换')
    expect(source).toContain("source: 'models'")
  })

  it('adds, changes, and removes model project members while protecting the owner', async () => {
    const wrapper = mount(ModelProjectDetailView, {
      global: { plugins: [ElementPlus], stubs: { RouterLink: true, ServerFilePicker: true } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('所有者')
    expect(wrapper.find('[data-test="remove-model-member-owner-id"]').exists()).toBe(false)
    await wrapper.get('[data-test="model-member-username"]').setValue('viewer')
    await wrapper.get('.member-form').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-test="toggle-model-member-editor-id"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="remove-model-member-editor-id"]').trigger('click')
    await flushPromises()

    expect(mocks.addMember).toHaveBeenCalledWith('project-id', 'viewer', 'viewer')
    expect(mocks.changeRole).toHaveBeenCalledWith('project-id', 'editor-id', 'viewer')
    expect(mocks.removeMember).toHaveBeenCalledWith('project-id', 'editor-id')
  })

  it('lets the system administrator maintain the official project without explicit members', async () => {
    mocks.getProject.mockResolvedValue({
      ...project,
      system_key: 'official_yolo11',
      access: { ...project.access, role: null, source: 'system_admin' },
    })
    const wrapper = mount(ModelProjectDetailView, {
      global: { plugins: [ElementPlus], stubs: { RouterLink: true, ServerFilePicker: true } },
    })
    await flushPromises()

    expect(wrapper.find('[data-test="add-model-member"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('管理员')
    expect(wrapper.text()).not.toContain('系统管理员访问')
    expect(wrapper.text()).toContain('编辑项目')
    expect(wrapper.text()).toContain('导入模型')
    expect(wrapper.text()).toContain('不能删除项目或配置成员')
  })
})
