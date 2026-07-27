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
    description_zh: '安全帽',
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
    description_zh: '人员',
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
    sessionStorage.clear()
    vi.mocked(listLabels).mockResolvedValue(structuredClone(labels))
    vi.mocked(createLabel).mockImplementation(async (_projectId, name, descriptionZh, color) => ({
      ...labels[0],
      id: 'new-id',
      name,
      description_zh: descriptionZh,
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

  it('renders the required columns and adds a bilingual label through the compact toolbar', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.findAll('.label-header > span').map((column) => column.text())).toEqual([
      '启用状态',
      '英文类别',
      '中文描述',
      '映射顺序',
      '操作',
    ])
    expect(wrapper.get('[data-test="order-helmet-id"]').text()).toBe('0')
    expect(wrapper.get<HTMLInputElement>('[data-test="name-helmet-id"]').element.value).toBe('helmet')
    expect(wrapper.get<HTMLInputElement>('[data-test="description-helmet-id"]').element.value).toBe('安全帽')
    const color = wrapper.get<HTMLInputElement>('[data-test="new-label-color"]').element.value
    expect(wrapper.get<HTMLInputElement>('[data-test="name-person-id"]').element.value).toBe('person')
    await wrapper.get('[data-test="new-label-name"]').setValue('dog')
    await wrapper.get('[data-test="new-label-description"]').setValue('狗')
    await wrapper.get('.label-create').trigger('submit')
    await flushPromises()

    expect(createLabel).toHaveBeenCalledWith('project-id', 'dog', '狗', color)
    expect(wrapper.get<HTMLInputElement>('[data-test="name-new-id"]').element.value).toBe('dog')
  })

  it('keeps the candidate color in session storage and advances it after creation', async () => {
    const first = mountView()
    await flushPromises()
    const colorInput = first.get<HTMLInputElement>('[data-test="new-label-color"]')
    await colorInput.setValue('#ef4444')
    await colorInput.trigger('change')
    expect(sessionStorage.getItem('vdw:label-color:project-id')).toBe('#ef4444')
    first.unmount()

    const second = mountView()
    await flushPromises()
    expect(second.get<HTMLInputElement>('[data-test="new-label-color"]').element.value).toBe('#ef4444')
    await second.get('[data-test="new-label-name"]').setValue('dog')
    await second.get('.label-create').trigger('submit')
    await flushPromises()

    expect(second.get<HTMLInputElement>('[data-test="new-label-color"]').element.value).not.toBe('#ef4444')
    expect(sessionStorage.getItem('vdw:label-color:project-id')).not.toBe('#ef4444')
  })

  it('retains the candidate color when creation fails', async () => {
    vi.mocked(createLabel).mockRejectedValueOnce(new Error('添加失败'))
    const wrapper = mountView()
    await flushPromises()
    const color = wrapper.get<HTMLInputElement>('[data-test="new-label-color"]').element.value

    await wrapper.get('[data-test="new-label-name"]').setValue('dog')
    await wrapper.get('.label-create').trigger('submit')
    await flushPromises()

    expect(wrapper.get<HTMLInputElement>('[data-test="new-label-color"]').element.value).toBe(color)
    expect(sessionStorage.getItem('vdw:label-color:project-id')).toBe(color)
  })

  it('edits the Chinese description inline', async () => {
    const wrapper = mountView('editor')
    await flushPromises()

    await wrapper.get('[data-test="description-helmet-id"]').setValue('防护头盔')
    await wrapper.get('[data-test="description-helmet-id"]').trigger('change')
    await flushPromises()

    expect(updateLabel).toHaveBeenCalledWith('project-id', labels[0], {
      description_zh: '防护头盔',
    })
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
    expect(wrapper.text()).toContain('安全帽')
    expect(wrapper.find('[data-test="new-label-name"]').exists()).toBe(false)
    expect(
      wrapper.get('[data-test="enabled-helmet-id"] input').attributes('aria-disabled'),
    ).toBe('true')
    expect(wrapper.find('[data-test="move-up-person-id"]').exists()).toBe(false)
  })
})
