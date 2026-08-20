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

  it('keeps the application scroll container while annotation opens and history moves', async () => {
    const project = {
      id: 'project-id', name: 'Dataset', description: '', creator_id: 'creator-id',
      creator_username: 'creator', role: 'editor', version: 1,
      created_at: '', updated_at: '',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: string | URL | Request) => {
        const path = String(input)
        let value: unknown
        if (path.includes('/setup/')) {
          value = { initialized: true }
        } else if (path.includes('/auth/status')) {
          value = { mode: 'multi', registration_enabled: false }
        } else if (path.includes('/auth/me')) {
          value = {
            id: 'editor-id', username: 'editor', status: 'active', is_system_admin: false,
          }
        } else if (path.includes('/projects/project-id/videos?')) {
          value = { items: [], page: 1, page_size: 50, total: 0 }
        } else if (path.endsWith('/projects/project-id')) {
          value = project
        } else if (path.includes('/projects?')) {
          value = { items: [project], page: 1, page_size: 5, total: 1 }
        } else if (path.endsWith('/model-projects') || path.endsWith('/training-tasks')) {
          value = []
        } else if (path.endsWith('/capabilities')) {
          value = {
            gpu: { available: true, reason: null, devices: [] },
            pytorch_cuda: { available: true, reason: null },
            features: {
              manual_annotation: { available: true, reason: null },
              yolo_auto_annotation: { available: true, reason: null },
              model_training: { available: true, reason: null },
            },
          }
        } else {
          throw new Error(`Unexpected request: ${path}`)
        }
        return Promise.resolve({ ok: true, json: async () => value })
      }),
    )
    const router = createAppRouter()
    await router.push('/projects/project-id/videos')
    await router.isReady()
    const wrapper = mount(App, {
      attachTo: document.body,
      global: {
        plugins: [router],
        stubs: { AnnotationWorkbenchView: true },
      },
    })
    await flushPromises()
    const scrollElement = wrapper.get('.app-content').element as HTMLElement
    scrollElement.scrollTop = 360

    await router.push({
      name: 'video-annotation',
      params: { id: 'project-id', videoId: 'video-id' },
      state: { annotationFromVideoList: true },
    })
    await flushPromises()

    expect(wrapper.find('.app-shell').exists()).toBe(true)
    expect(document.body.querySelector('.focus-layout')).not.toBeNull()
    expect(wrapper.get('.app-content').element).toBe(scrollElement)
    expect(scrollElement.scrollTop).toBe(360)

    await new Promise<void>((resolve) => {
      const remove = router.afterEach(() => { remove(); resolve() })
      router.back()
    })
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('project-videos')
    expect(wrapper.get('.app-content').element).toBe(scrollElement)
    expect(scrollElement.scrollTop).toBe(360)

    await new Promise<void>((resolve) => {
      const remove = router.afterEach(() => { remove(); resolve() })
      router.forward()
    })
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('video-annotation')
    expect(wrapper.get('.app-content').element).toBe(scrollElement)

    wrapper.unmount()
  })
})
