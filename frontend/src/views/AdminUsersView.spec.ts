import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AdminUsersView from './AdminUsersView.vue'

const admin = {
  id: 'admin-id', username: 'admin', status: 'active', is_system_admin: true,
  must_change_password: false, created_at: '2026-09-20T00:00:00Z',
}
const worker = {
  id: 'worker-id', username: 'worker', status: 'active', is_system_admin: false,
  must_change_password: true, created_at: '2026-09-20T00:00:00Z',
}
const page = (items = [admin, worker]) => ({ items, page: 1, page_size: 50, total: items.length })

beforeEach(() => vi.restoreAllMocks())

describe('AdminUsersView', () => {
  it('creates an account and reveals the initial password once', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => page() })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...worker, initial_password: 'random-initial-password' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => page() })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(AdminUsersView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.get('[data-test="create-user"]').trigger('click')
    await wrapper.get('[data-test="new-username"]').setValue('worker')
    await wrapper.get('[data-test="submit-user"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/admin/users', expect.objectContaining({ method: 'POST' }))
    expect((document.body.querySelector('[data-test="initial-password"]') as HTMLInputElement).value)
      .toBe('random-initial-password')
    wrapper.unmount()
  })

  it('resets an ordinary user password and protects the administrator row', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => page() })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...worker, initial_password: 'new-random-password' }) })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(AdminUsersView, { attachTo: document.body, global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.find('[data-test="disable-admin-id"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="reset-admin-id"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('审核')
    await wrapper.get('[data-test="reset-worker-id"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/admin/users/worker-id/reset-password',
      expect.objectContaining({ method: 'POST' }),
    )
    expect((document.body.querySelector('[data-test="initial-password"]') as HTMLInputElement).value)
      .toBe('new-random-password')
    wrapper.unmount()
  })

  it('shows success feedback after copying the initial password', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => page() })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...worker, initial_password: 'new-random-password' }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(AdminUsersView, {
      attachTo: document.body,
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    await wrapper.get('[data-test="reset-worker-id"]').trigger('click')
    await flushPromises()

    const button = document.body.querySelector('[data-test="copy-initial-password"]') as HTMLElement
    await button.click()
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith('new-random-password')
    expect(button.getAttribute('title')).toBe('已复制')
    expect(document.body.textContent).toContain('初始密码已复制')
    wrapper.unmount()
  })

  it('reports clipboard failures', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
    })
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => page() })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...worker, initial_password: 'new-random-password' }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(AdminUsersView, {
      attachTo: document.body,
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    await wrapper.get('[data-test="reset-worker-id"]').trigger('click')
    await flushPromises()

    ;(document.body.querySelector('[data-test="copy-initial-password"]') as HTMLElement).click()
    await flushPromises()

    expect(document.body.textContent).toContain('复制失败，请手动选择密码复制')
    wrapper.unmount()
  })
})
