import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ReadyView from './ReadyView.vue'

const replace = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ replace }) }))

beforeEach(() => {
  replace.mockReset()
  vi.restoreAllMocks()
})

describe('ReadyView', () => {
  it('shows account and administrator actions and logs out', async () => {
    const fetchMock = vi.fn().mockImplementation((path: string) => {
      if (path.endsWith('/me')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 'admin-id',
            username: 'admin',
            status: 'active',
            is_system_admin: true,
          }),
        })
      }
      return Promise.resolve({ ok: true, status: 204 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReadyView, {
      global: {
        plugins: [ElementPlus],
        stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } },
      },
    })
    await flushPromises()

    expect(wrapper.get('[data-test="account-link"]').attributes('href')).toBe('/account')
    expect(wrapper.get('[data-test="users-link"]').attributes('href')).toBe('/admin/users')
    await wrapper.get('[data-test="logout"]').trigger('click')
    await flushPromises()
    expect(replace).toHaveBeenCalledWith('/login')
  })
})
