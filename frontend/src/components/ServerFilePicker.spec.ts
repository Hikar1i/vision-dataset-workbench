import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { FilesystemPage, FilesystemQuery } from '../api/filesystem'
import ServerFilePicker from './ServerFilePicker.vue'

const rootPage = (): FilesystemPage => ({
  path: '~',
  parent: null,
  items: [
    { name: 'clips', path: 'clips', type: 'dir', size: null },
    { name: 'fire-det.mp4', path: 'fire-det.mp4', type: 'mp4', size: 10 },
    { name: 'origin.MOV', path: 'origin.MOV', type: 'mov', size: 20 },
  ],
  page: 1,
  page_size: 100,
  total: 3,
})

afterEach(() => {
  document.body.innerHTML = ''
  vi.useRealTimers()
})

describe('ServerFilePicker', () => {
  it('selects visible files or one directory without selecting directory rows', async () => {
    const loadEntries = vi.fn().mockResolvedValue(rootPage())
    const wrapper = mount(ServerFilePicker, {
      props: {
        modelValue: [],
        selectedDirectory: '',
        mode: 'multiple-files-or-directory',
        allowedExtensions: ['mp4', 'mov'],
        loadEntries,
      },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    expect(wrapper.get('[data-test="entry-type-clips"]').text()).toBe('dir')
    expect(wrapper.get('[data-test="entry-type-fire-det.mp4"]').text()).toBe('mp4')
    expect(wrapper.find('[data-test="select-file-clips"]').exists()).toBe(false)

    await wrapper.get('[data-test="select-visible-files"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([
      ['fire-det.mp4', 'origin.MOV'],
    ])

    await wrapper.get('[data-test="select-directory-clips"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([[]])
    expect(wrapper.emitted('update:selectedDirectory')?.at(-1)).toEqual(['clips'])
  })

  it('uses single-file and directory modes without file checkboxes', async () => {
    const loadEntries = vi.fn().mockResolvedValue(rootPage())
    const filePicker = mount(ServerFilePicker, {
      props: { modelValue: '', mode: 'single-file', allowedExtensions: ['pt'], loadEntries },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    await filePicker.get('[data-test="choose-file-fire-det.mp4"]').trigger('click')
    expect(filePicker.emitted('update:modelValue')?.at(-1)).toEqual(['fire-det.mp4'])
    expect(filePicker.find('[data-test="select-visible-files"]').exists()).toBe(false)

    const directoryPicker = mount(ServerFilePicker, {
      props: { modelValue: '', mode: 'directory', loadEntries },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    expect(directoryPicker.emitted('update:modelValue')?.at(-1)).toEqual(['.'])
    expect(directoryPicker.find('[data-test="choose-file-fire-det.mp4"]').exists()).toBe(false)
  })

  it('debounces search and ignores stale directory responses', async () => {
    vi.useFakeTimers()
    let resolveClips: ((value: FilesystemPage) => void) | undefined
    const queries: FilesystemQuery[] = []
    const loadEntries = vi.fn((query: FilesystemQuery): Promise<FilesystemPage> => {
      queries.push(query)
      if (query.path === 'clips') {
        return new Promise((resolve) => { resolveClips = resolve })
      }
      if (query.search === 'fire') {
        return Promise.resolve({ ...rootPage(), items: [rootPage().items[1]!], total: 1 })
      }
      return Promise.resolve(rootPage())
    })
    const wrapper = mount(ServerFilePicker, {
      props: { modelValue: '', mode: 'single-file', allowedExtensions: ['mp4'], loadEntries },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    await wrapper.get('[data-test="open-directory-clips"]').trigger('click')
    await wrapper.get('input[data-test="filesystem-search"]').setValue('fire')
    await vi.advanceTimersByTimeAsync(250)
    await flushPromises()
    resolveClips?.({ ...rootPage(), path: '~/clips', items: [], total: 0 })
    await flushPromises()

    expect(queries.at(-1)).toMatchObject({ path: '.', search: 'fire' })
    expect(wrapper.find('[data-test="entry-fire-det.mp4"]').exists()).toBe(true)
  })

  it('creates and enters a directory with the injected writer', async () => {
    const loadEntries = vi.fn().mockResolvedValue(rootPage())
    const createDirectory = vi.fn().mockResolvedValue({ path: 'new', display_path: '~/new' })
    const wrapper = mount(ServerFilePicker, {
      props: {
        modelValue: '',
        mode: 'directory',
        allowCreateDirectory: true,
        loadEntries,
        createDirectory,
      },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    await wrapper.get('[data-test="new-directory"]').trigger('click')
    const overlay = new DOMWrapper(document.body)
    await overlay.get('[data-test="directory-name"]').setValue('new')
    await overlay.get('[data-test="create-directory"]').trigger('click')
    await flushPromises()

    expect(createDirectory).toHaveBeenCalledWith('.', 'new')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['new'])
  })
})
