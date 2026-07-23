import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountView from './AccountView.vue'

const replace = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ replace }) }))

beforeEach(() => {
  replace.mockReset()
  vi.restoreAllMocks()
})

describe('AccountView', () => {
  it('changes the password and returns to the workbench', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 'admin-id',
        username: 'admin',
        status: 'active',
        is_system_admin: true,
      }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(AccountView, { global: { plugins: [ElementPlus] } })

    await wrapper.get('[data-test="current-password"]').setValue('current password')
    await wrapper.get('[data-test="new-password"]').setValue('new correct horse battery')
    await wrapper
      .get('[data-test="password-confirmation"]')
      .setValue('new correct horse battery')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/password',
      expect.objectContaining({ method: 'PUT', credentials: 'same-origin' }),
    )
    expect(replace).toHaveBeenCalledWith('/projects')
  })

  it('keeps submission disabled while new passwords differ', async () => {
    const wrapper = mount(AccountView, { global: { plugins: [ElementPlus] } })
    await wrapper.get('[data-test="current-password"]').setValue('current password')
    await wrapper.get('[data-test="new-password"]').setValue('new correct horse battery')
    await wrapper.get('[data-test="password-confirmation"]').setValue('different password')
    expect(wrapper.get('[data-test="save-password"]').attributes('disabled')).toBeDefined()
  })
})
