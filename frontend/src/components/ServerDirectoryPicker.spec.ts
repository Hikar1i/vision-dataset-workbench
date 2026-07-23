import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import ServerDirectoryPicker from './ServerDirectoryPicker.vue'

describe('ServerDirectoryPicker', () => {
  it('lists directories and creates a new directory', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          path: '~',
          parent: null,
          items: [{ name: 'datasets', path: 'datasets' }],
          page: 1,
          page_size: 100,
          total: 1,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          path: '~/datasets',
          parent: '.',
          items: [],
          page: 1,
          page_size: 100,
          total: 0,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ path: 'datasets/new', display_path: '~/datasets/new' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          path: '~/datasets/new',
          parent: 'datasets',
          items: [],
          page: 1,
          page_size: 100,
          total: 0,
        }),
      })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ServerDirectoryPicker, {
      props: { token: 'secret' },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    await wrapper.get('[data-path="datasets"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="new-directory"]').trigger('click')
    await wrapper.get('[data-test="directory-name"]').setValue('new')
    await wrapper.get('[data-test="create-directory"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['datasets/new'])
  })
})
