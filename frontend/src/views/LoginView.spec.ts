import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LoginView from './LoginView.vue'

const replace = vi.fn()

vi.mock('vue-router', () => ({ useRouter: () => ({ replace }) }))

beforeEach(() => {
  replace.mockReset()
  vi.restoreAllMocks()
})

describe('LoginView', () => {
  it('logs in with a same-origin session and opens the workbench', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ mode: 'multi', registration_enabled: true }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'admin-id',
          username: 'admin',
          status: 'active',
          is_system_admin: true,
        }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(LoginView, {
      global: {
        plugins: [ElementPlus],
        stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } },
      },
    })
    await flushPromises()

    await wrapper.get('[data-test="username"]').setValue('admin')
    await wrapper.get('[data-test="password"]').setValue('correct horse battery staple')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/auth/login',
      expect.objectContaining({ method: 'POST', credentials: 'same-origin' }),
    )
    expect(wrapper.get('[data-test="register-link"]').attributes('href')).toBe('/register')
    expect(replace).toHaveBeenCalledWith('/ready')
  })

  it('shows the server login error', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ mode: 'single', registration_enabled: false }),
        })
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          json: async () => ({ detail: 'invalid username or password' }),
        }),
    )
    const wrapper = mount(LoginView, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await wrapper.get('[data-test="username"]').setValue('admin')
    await wrapper.get('[data-test="password"]').setValue('wrong password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('invalid username or password')
    expect(wrapper.find('[data-test="register-link"]').exists()).toBe(false)
  })
})
