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
        ServerFilePicker: {
          emits: ['update:modelValue', 'update:selectedDirectory'],
          template: `
            <div>
              <button data-test="pick-files" @click="$emit('update:modelValue', ['clips/one.mp4', 'clips/two.mp4'])">files</button>
              <button data-test="pick-directory" @click="$emit('update:selectedDirectory', 'clips')">directory</button>
            </div>
          `,
        },
      },
    },
  })
}

describe('ImportVideosDialog', () => {
  it('imports selected local files directly without a preview step', async () => {
    const batch = { accepted: [{ video: { id: 'video' }, task: { id: 'task' } }], skipped: [], rejected: [] }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 202, json: async () => batch })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountDialog()
    await flushPromises()

    expect(wrapper.find('[data-test="preview-local"]').exists()).toBe(false)
    await wrapper.get('[data-test="pick-files"]').trigger('click')
    expect(wrapper.text()).toContain('导入选中的 2 个视频')
    await wrapper.get('[data-test="submit-import"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/projects/project-id/imports/local',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ paths: ['clips/one.mp4', 'clips/two.mp4'] }),
      }),
    )
    expect(wrapper.emitted('submitted')?.[0]).toEqual([batch])
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('resolves only the selected directory before importing its videos', async () => {
    const batch = { accepted: [], skipped: [], rejected: [] }
    const fetchMock = vi.fn().mockImplementation((path: string) => Promise.resolve({
      ok: true,
      status: path.endsWith('/preview') ? 200 : 202,
      json: async () => path.endsWith('/preview')
        ? [
            { path: 'clips/one.mp4', name: 'one.mp4', size: 10 },
            { path: 'clips/two.mp4', name: 'two.mp4', size: 20 },
          ]
        : batch,
    }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountDialog()
    await flushPromises()

    await wrapper.get('[data-test="pick-directory"]').trigger('click')
    expect(wrapper.text()).toContain('导入选中目录下的视频')
    await wrapper.get('[data-test="submit-import"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/projects/project-id/imports/local',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ paths: ['clips/one.mp4', 'clips/two.mp4'] }),
      }),
    )
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
