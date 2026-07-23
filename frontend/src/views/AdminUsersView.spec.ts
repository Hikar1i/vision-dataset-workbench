import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AdminUsersView from './AdminUsersView.vue'

const pendingUser = {
  id: 'user-id',
  username: 'colleague',
  status: 'pending',
  is_system_admin: false,
  created_at: '2026-07-23T00:00:00Z',
  reviewed_at: null,
}

beforeEach(() => vi.restoreAllMocks())

describe('AdminUsersView', () => {
  it('approves one pending user without reloading the list', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [pendingUser], page: 1, page_size: 50, total: 1 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ...pendingUser,
          status: 'active',
          reviewed_at: '2026-07-23T01:00:00Z',
        }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(AdminUsersView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.get('[data-test="approve-user-id"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/admin/users/user-id/approve',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(wrapper.text()).toContain('正常')
  })

  it('shows a server conflict when the last administrator cannot be disabled', async () => {
    const admin = {
      ...pendingUser,
      id: 'admin-id',
      username: 'admin',
      status: 'active',
      is_system_admin: true,
    }
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ items: [admin], page: 1, page_size: 50, total: 1 }),
        })
        .mockResolvedValueOnce({
          ok: false,
          status: 409,
          json: async () => ({ detail: 'cannot disable the last active administrator' }),
        }),
    )
    const wrapper = mount(AdminUsersView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.get('[data-test="disable-admin-id"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('cannot disable the last active administrator')
  })
})
