import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createLabel,
  deleteLabel,
  listLabels,
  reorderLabels,
  updateLabel,
} from '../api/labels'
import ProjectLabelsView from './ProjectLabelsView.vue'

vi.mock('../api/labels', () => ({
  createLabel: vi.fn(),
  deleteLabel: vi.fn(),
  listLabels: vi.fn(),
  reorderLabels: vi.fn(),
  updateLabel: vi.fn(),
}))

const project = {
  id: 'project-id',
  name: '安全装备',
  description: '',
  creator_id: 'creator-id',
  creator_username: 'creator',
  role: 'owner' as const,
  version: 1,
  created_at: '2026-07-27T00:00:00Z',
  updated_at: '2026-07-27T00:00:00Z',
}

const labels = [
  {
    id: 'helmet-id',
    name: 'helmet',
    color: '#16866f',
    sort_order: 0,
    enabled: true,
    version: 1,
    created_at: '2026-07-27T00:00:00Z',
    updated_at: '2026-07-27T00:00:00Z',
  },
  {
    id: 'person-id',
    name: 'person',
    color: '#17212b',
    sort_order: 1,
    enabled: true,
    version: 1,
    created_at: '2026-07-27T00:00:00Z',
    updated_at: '2026-07-27T00:00:00Z',
  },
]

function mountView(role: 'owner' | 'editor' | 'viewer' = 'owner') {
  return mount(ProjectLabelsView, {
    props: { project: { ...project, role } },
    global: { plugins: [ElementPlus] },
  })
}

describe('ProjectLabelsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(listLabels).mockResolvedValue(structuredClone(labels))
    vi.mocked(createLabel).mockImplementation(async (_projectId, name, color) => ({
      ...labels[0],
      id: 'new-id',
      name,
      color,
      sort_order: 2,
    }))
    vi.mocked(updateLabel).mockImplementation(async (_projectId, label, changes) => ({
      ...label,
      ...changes,
      version: label.version + 1,
    }))
    vi.mocked(reorderLabels).mockResolvedValue([labels[1], labels[0]])
    vi.mocked(deleteLabel).mockResolvedValue()
  })

  it('loads labels and adds one through the compact toolbar', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get<HTMLInputElement>('[data-test="name-helmet-id"]').element.value).toBe('helmet')
    expect(wrapper.get<HTMLInputElement>('[data-test="name-person-id"]').element.value).toBe('person')
    await wrapper.get('[data-test="new-label-name"]').setValue('dog')
    await wrapper.get('.label-create').trigger('submit')
    await flushPromises()

    expect(createLabel).toHaveBeenCalledWith('project-id', 'dog', '#16866f')
    expect(wrapper.get<HTMLInputElement>('[data-test="name-new-id"]').element.value).toBe('dog')
  })

  it('updates status and persists an atomic reorder', async () => {
    const wrapper = mountView('editor')
    await flushPromises()

    await wrapper.get('[data-test="enabled-helmet-id"]').trigger('click')
    await flushPromises()
    expect(updateLabel).toHaveBeenCalledWith('project-id', labels[0], { enabled: false })

    await wrapper.get('[data-test="move-up-person-id"]').trigger('click')
    await flushPromises()
    expect(reorderLabels).toHaveBeenCalledWith('project-id', ['person-id', 'helmet-id'])
  })

  it('renders viewer labels without write controls', async () => {
    const wrapper = mountView('viewer')
    await flushPromises()

    expect(wrapper.text()).toContain('helmet')
    expect(wrapper.find('[data-test="new-label-name"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="enabled-helmet-id"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="move-up-person-id"]').exists()).toBe(false)
  })
})
