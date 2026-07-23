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
})
