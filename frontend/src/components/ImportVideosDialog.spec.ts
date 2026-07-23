import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ImportVideosDialog from './ImportVideosDialog.vue'

beforeEach(() => vi.restoreAllMocks())

function mountDialog() {
  return mount(ImportVideosDialog, {
    props: { modelValue: true, projectId: 'project-id' },
    global: {
      plugins: [ElementPlus],
      stubs: {
        ElDialog: {
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template: '<section v-if="modelValue"><slot /><slot name="footer" /></section>',
        },
        ServerVideoPicker: {
          emits: ['update:modelValue'],
          template: '<button data-test="pick" @click="$emit(\'update:modelValue\', \'clips\')">pick</button>',
        },
      },
    },
  })
}

describe('ImportVideosDialog', () => {
  it('previews selected local files and creates tasks without waiting for workers', async () => {
    const batch = { accepted: [{ video: { id: 'video' }, task: { id: 'task' } }], skipped: [], rejected: [] }
    const fetchMock = vi.fn().mockImplementation((_path: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body || '{}'))
      return Promise.resolve({
        ok: true,
        status: body.paths ? 202 : 200,
        json: async () =>
          body.paths
            ? batch
            : [{ path: 'clips/one.mp4', name: 'one.mp4', size: 10 }],
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountDialog()
    await flushPromises()

    await wrapper.get('[data-test="pick"]').trigger('click')
    await wrapper.get('[data-test="preview-local"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('one.mp4')
    await wrapper.get('[data-test="submit-import"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/projects/project-id/imports/local',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(wrapper.emitted('submitted')?.[0]).toEqual([batch])
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('previews a remote playlist before submitting selected URLs', async () => {
    const fetchMock = vi.fn().mockImplementation((_path: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body || '{}'))
      return Promise.resolve({
        ok: true,
        status: body.items ? 202 : 200,
        json: async () =>
          body.items
            ? { accepted: [], skipped: [], rejected: [] }
            : [{
                title: 'Remote one',
                url: 'https://example.test/one',
                duration: 3,
                extractor: 'youtube',
                external_id: 'one',
                playlist: 'List',
                playlist_index: 1,
              }],
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.get('#tab-remote').trigger('click')
    await wrapper.get('[data-test="remote-url"]').setValue('https://example.test/list')
    await wrapper.get('[data-test="preview-remote"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Remote one')
    await wrapper.get('[data-test="submit-import"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/projects/project-id/imports/remote',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
