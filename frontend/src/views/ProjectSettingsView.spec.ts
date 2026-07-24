import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectSettingsView from './ProjectSettingsView.vue'

const project = {
  id: 'project-id',
  name: '缺陷视频',
  description: '产线 A',
  creator_id: 'creator-id',
  creator_username: 'creator',
  role: 'owner',
  version: 1,
  created_at: '2026-07-23T00:00:00Z',
  updated_at: '2026-07-23T00:00:00Z',
}

const owner = {
  id: 'creator-id',
  username: 'creator',
  status: 'active',
  role: 'owner',
  created_at: '2026-07-23T00:00:00Z',
}

beforeEach(() => vi.restoreAllMocks())

function mountView(role: 'owner' | 'editor' | 'viewer' = 'owner') {
  return mount(ProjectSettingsView, {
    props: { project: { ...project, role } },
    global: {
      plugins: [ElementPlus],
      stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } },
    },
  })
}

function readMock() {
  return vi.fn().mockImplementation((path: string) =>
    Promise.resolve({
      ok: true,
      json: async () => (path.endsWith('/members') ? [owner] : project),
    }),
  )
}

describe('ProjectSettingsView', () => {
  it('lets the owner edit metadata and add a member', async () => {
    const added = {
      id: 'viewer-id',
      username: 'viewer',
      status: 'active',
      role: 'viewer',
      created_at: '2026-07-23T01:00:00Z',
    }
    const fetchMock = vi.fn().mockImplementation((path: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 201, json: async () => added })
      }
      if (init?.method === 'PATCH') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ ...project, name: '新名称', version: 2 }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => (path.endsWith('/members') ? [owner] : project),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-test="project-name"]').setValue('新名称')
    await wrapper.get('[data-test="save-project"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/projects/project-id',
      expect.objectContaining({ method: 'PATCH' }),
    )

    await wrapper.get('[data-test="member-username"]').setValue('viewer')
    await wrapper.get('.member-form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('viewer')
    expect(wrapper.find('[data-test="remove-creator-id"]').exists()).toBe(false)
  })

  it('lets editors edit but hides member controls, and makes viewers read-only', async () => {
    vi.stubGlobal('fetch', readMock())
    const editor = mountView('editor')
    await flushPromises()
    expect(editor.find('[data-test="project-name"]').exists()).toBe(true)
    expect(editor.find('[data-test="member-username"]').exists()).toBe(false)

    vi.stubGlobal('fetch', readMock())
    const viewer = mountView('viewer')
    await flushPromises()
    expect(viewer.find('[data-test="project-name"]').exists()).toBe(false)
    expect(viewer.text()).toContain('产线 A')
  })

  it('shows a version conflict and reloads project data', async () => {
    let projectReads = 0
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string, init?: RequestInit) => {
        if (init?.method === 'PATCH') {
          return Promise.resolve({
            ok: false,
            status: 409,
            json: async () => ({ detail: 'project was modified by another user' }),
          })
        }
        if (path.endsWith('/members')) {
          return Promise.resolve({ ok: true, json: async () => [owner] })
        }
        projectReads += 1
        return Promise.resolve({
          ok: true,
          json: async () => ({ ...project, version: projectReads }),
        })
      }),
    )
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-test="project-name"]').setValue('冲突名称')
    await wrapper.get('[data-test="save-project"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('project was modified by another user')
    expect(projectReads).toBe(1)
  })
})
