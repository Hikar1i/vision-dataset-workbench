import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import RegisterView from './RegisterView.vue'

const replace = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ replace }) }))

beforeEach(() => {
  replace.mockReset()
  vi.restoreAllMocks()
})

describe('RegisterView', () => {
  it('submits a registration and shows the approval state', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ mode: 'multi', registration_enabled: true }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({ id: 'user-id', username: 'colleague', status: 'pending' }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(RegisterView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.get('[data-test="username"]').setValue('colleague')
    await wrapper.get('[data-test="password"]').setValue('correct horse battery staple')
    await wrapper
      .get('[data-test="password-confirmation"]')
      .setValue('correct horse battery staple')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/registrations',
      expect.objectContaining({ method: 'POST', credentials: 'same-origin' }),
    )
    expect(wrapper.text()).toContain('等待管理员审批')
  })

  it('returns to login when registration is closed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ mode: 'multi', registration_enabled: false }),
      }),
    )
    mount(RegisterView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(replace).toHaveBeenCalledWith('/login')
  })
})
