import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectsView from './ProjectsView.vue'

const push = vi.fn()
const replace = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push, replace }) }))

const admin = {
  id: 'admin-id',
  username: 'admin',
  status: 'active',
  is_system_admin: true,
}

beforeEach(() => {
  push.mockReset()
  replace.mockReset()
  vi.restoreAllMocks()
})

function mountView() {
  return mount(ProjectsView, {
    global: {
      plugins: [ElementPlus],
      stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } },
    },
  })
}

describe('ProjectsView', () => {
  it('shows an actionable empty state without a second global header', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            path.endsWith('/me')
              ? admin
              : { items: [], page: 1, page_size: 50, total: 0 },
        }),
      ),
    )
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('还没有项目')
    expect(wrapper.get('[data-test="page-title"]').text()).toBe('数据集项目')
    expect(wrapper.find('.topbar').exists()).toBe(false)
  })

  it('creates a project and opens its video workspace', async () => {
    const created = {
      id: 'project-id',
      name: '缺陷视频',
      description: '产线 A',
      creator_id: 'admin-id',
      creator_username: 'admin',
      role: 'owner',
      version: 1,
      created_at: '2026-07-23T00:00:00Z',
      updated_at: '2026-07-23T00:00:00Z',
    }
    const fetchMock = vi.fn().mockImplementation((path: string, init?: RequestInit) => {
      if (path.endsWith('/me')) return Promise.resolve({ ok: true, json: async () => admin })
      if (init?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 201, json: async () => created })
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ items: [], page: 1, page_size: 50, total: 0 }),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-test="show-create"]').trigger('click')
    await wrapper.get('[data-test="project-name"]').setValue('缺陷视频')
    await wrapper.get('[data-test="project-description"]').setValue('产线 A')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/projects',
      expect.objectContaining({ method: 'POST', credentials: 'same-origin' }),
    )
    expect(push).toHaveBeenCalledWith('/projects/project-id/videos')
  })

  it('renders project identity, role and settings link', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            path.endsWith('/me')
              ? admin
              : {
                  items: [
                    {
                      id: '12345678-project',
                      name: '项目一',
                      description: '',
                      creator_id: 'admin-id',
                      creator_username: 'admin',
                      role: 'owner',
                      version: 1,
                      created_at: '2026-07-23T00:00:00Z',
                      updated_at: '2026-07-23T00:00:00Z',
                    },
                  ],
                  page: 1,
                  page_size: 50,
                  total: 1,
                },
        }),
      ),
    )
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('12345678')
    expect(wrapper.text()).toContain('所有者')
    expect(wrapper.get('[data-test="open-12345678-project"]').attributes('href')).toBe(
      '/projects/12345678-project/videos',
    )
  })
})
