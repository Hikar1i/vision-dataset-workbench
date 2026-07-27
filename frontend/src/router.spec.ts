import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'
import { createAppRouter } from './router'

beforeEach(() => vi.restoreAllMocks())

describe('setup routing', () => {
  it('redirects an uninitialized instance to setup', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ initialized: false }) }),
    )
    const router = createAppRouter()
    await router.push('/')
    await router.isReady()
    mount(App, { global: { plugins: [router] } })
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/setup')
  })

  it('redirects an initialized anonymous user to login', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) => {
        if (path.includes('/setup/')) {
          return Promise.resolve({ ok: true, json: async () => ({ initialized: true }) })
        }
        if (path.includes('/auth/status')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ mode: 'multi', registration_enabled: false }),
          })
        }
        return Promise.resolve({
          ok: false,
          status: 401,
          json: async () => ({ detail: 'authentication required' }),
        })
      }),
    )
    const router = createAppRouter()
    await router.push('/ready')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('redirects an authenticated user away from login', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) => {
        if (path.includes('/setup/')) {
          return Promise.resolve({ ok: true, json: async () => ({ initialized: true }) })
        }
        if (path.includes('/auth/status')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ mode: 'multi', registration_enabled: false }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 'admin-id',
            username: 'admin',
            status: 'active',
            is_system_admin: true,
          }),
        })
      }),
    )
    const router = createAppRouter()
    await router.push('/login')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/projects')
  })

  it('renders annotation in the focus layout without the application sidebar', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) => {
        if (path.includes('/setup/')) {
          return Promise.resolve({ ok: true, json: async () => ({ initialized: true }) })
        }
        if (path.includes('/auth/status')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ mode: 'multi', registration_enabled: false }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: 'editor-id',
            username: 'editor',
            status: 'active',
            is_system_admin: false,
          }),
        })
      }),
    )
    const router = createAppRouter()
    await router.push('/projects/project-id/videos/video-id/annotation')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('.focus-layout').exists()).toBe(true)
    expect(wrapper.find('.app-shell').exists()).toBe(false)
  })
})
