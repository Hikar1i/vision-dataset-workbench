import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ModelProject } from '../api/models'
import ModelProjectMembersPanel from './ModelProjectMembersPanel.vue'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  add: vi.fn(),
  change: vi.fn(),
  remove: vi.fn(),
}))

vi.mock('../api/models', () => ({
  listModelProjectMembers: mocks.list,
  addModelProjectMember: mocks.add,
  changeModelProjectMemberRole: mocks.change,
  removeModelProjectMember: mocks.remove,
}))

const owner = { id: 'owner-id', username: 'owner', status: 'active', role: 'owner', created_at: '' }
const editor = { id: 'editor-id', username: 'editor', status: 'active', role: 'editor', created_at: '' }
const project: ModelProject = {
  id: 'project-id', name: 'Models', description: '', series_type: 'archive',
  system_key: null, created_by_id: 'owner-id', version: 1, can_manage: true,
  access: {
    role: 'owner', source: 'owner',
    permissions: ['project.read', 'project.update', 'project.members.manage', 'project.delete', 'artifact.read', 'artifact.download', 'artifact.consume', 'task.read', 'task.execute'],
  },
  created_at: '', updated_at: '', tags: [],
}

describe('ModelProjectMembersPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.list.mockResolvedValue([owner, editor])
    mocks.add.mockResolvedValue({ ...editor, id: 'viewer-id', username: 'viewer', role: 'viewer' })
    mocks.change.mockResolvedValue({ ...editor, role: 'viewer' })
    mocks.remove.mockResolvedValue(undefined)
  })

  it('manages non-owner members through the model project API', async () => {
    const wrapper = mount(ModelProjectMembersPanel, {
      props: { project, scopeDescription: '授权覆盖整个模型项目。' },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    expect(wrapper.find('[data-test="remove-model-member-owner-id"]').exists()).toBe(false)
    await wrapper.get('[data-test="model-member-username"]').setValue('viewer')
    await wrapper.get('.member-form').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-test="toggle-model-member-editor-id"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="remove-model-member-editor-id"]').trigger('click')
    await flushPromises()

    expect(mocks.add).toHaveBeenCalledWith('project-id', 'viewer', 'viewer')
    expect(mocks.change).toHaveBeenCalledWith('project-id', 'editor-id', 'viewer')
    expect(mocks.remove).toHaveBeenCalledWith('project-id', 'editor-id')
  })

  it('shows implicit read-only access without querying members for a system project', async () => {
    const wrapper = mount(ModelProjectMembersPanel, {
      props: {
        project: {
          ...project,
          system_key: 'official_yolo11',
          access: { role: 'viewer', source: 'system_resource', permissions: ['project.read'] },
        },
        scopeDescription: '授权覆盖整个模型项目。',
      },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    expect(mocks.list).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="add-model-member"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('所有正常账号自动获得只读访问')
  })
})
