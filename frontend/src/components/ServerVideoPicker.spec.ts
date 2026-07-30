import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ServerVideoPicker from './ServerVideoPicker.vue'

beforeEach(() => vi.restoreAllMocks())
afterEach(() => {
  document.body.innerHTML = ''
})

describe('ServerVideoPicker', () => {
  it('browses directories, selects video files and creates a directory', async () => {
    const fetchMock = vi.fn().mockImplementation((path: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          status: 201,
          json: async () => ({ path: 'new', display_path: '~/new' }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          path: path.includes('path=new') ? '~/new' : '~',
          parent: path.includes('path=new') ? '.' : null,
          items: path.includes('path=new')
            ? []
            : [
                { name: 'clips', path: 'clips', type: 'directory', size: null },
                { name: 'one.mp4', path: 'one.mp4', type: 'file', size: 10 },
              ],
          page: 1,
          page_size: 100,
          total: 2,
        }),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ServerVideoPicker, {
      props: { modelValue: '' },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    await wrapper.get('[data-test="entry-one.mp4"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['one.mp4'])

    await wrapper.get('[data-test="new-directory"]').trigger('click')
    const overlay = new DOMWrapper(document.body)
    await overlay.get('[data-test="directory-name"]').setValue('new')
    await overlay.get('[data-test="create-directory"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/filesystem/directories',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['new'])
  })

  it('selects multiple videos or one directory without exposing directory creation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        path: '~',
        parent: null,
        items: [
          { name: 'clips', path: 'clips', type: 'directory', size: null },
          { name: 'one.mp4', path: 'one.mp4', type: 'file', size: 10 },
        ],
        page: 1,
        page_size: 100,
        total: 2,
      }),
    }))
    const wrapper = mount(ServerVideoPicker, {
      props: {
        modelValue: [],
        selectedDirectory: '',
        multiple: true,
        allowCreate: false,
      },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    await wrapper.get('[data-test="select-directory-clips"]').trigger('click')
    expect(wrapper.emitted('update:selectedDirectory')?.at(-1)).toEqual(['clips'])
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([[]])

    await wrapper.get('[data-test="select-file-one.mp4"]').trigger('click')
    expect(wrapper.emitted('update:selectedDirectory')?.at(-1)).toEqual([''])
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([['one.mp4']])
    expect(wrapper.find('[data-test="new-directory"]').exists()).toBe(false)
  })
})
