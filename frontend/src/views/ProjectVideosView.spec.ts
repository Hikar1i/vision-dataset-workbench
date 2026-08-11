import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectVideosView from './ProjectVideosView.vue'

const { routerPush } = vi.hoisted(() => ({ routerPush: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: routerPush }) }))

const project = {
  id: 'project-id',
  name: '缺陷视频',
  description: '产线 A',
  creator_id: 'creator-id',
  creator_username: 'creator',
  role: 'viewer',
  version: 1,
  created_at: '2026-07-23T00:00:00Z',
  updated_at: '2026-07-23T00:00:00Z',
}

const video = {
  id: 'video-id',
  short_code: '7K3M9Q2X',
  source_type: 'local',
  title: 'camera-01',
  source_name: 'camera-01.mp4',
  source_url: null,
  duration: 65,
  width: 1920,
  height: 1080,
  fps: 25,
  total_frames: 1625,
  file_size: 1048576,
  status: 'ready',
  enabled: true,
  version: 2,
  created_at: '2026-07-23T01:00:00Z',
  updated_at: '2026-07-23T01:00:00Z',
  sampling: {
    id: 'plan-id', state: 'sampled', mode: 'target_frames', parameters: { minimum: 50, maximum: 200 },
    output_format: 'jpg', output_quality: 2, computed_interval: null, expected_frames: 50,
    extracted_frames: 50, enabled_frames: 48, version: 1, applied_version: 1,
    generation: 1, frame_revision: 2, updated_at: '2026-07-23T01:00:00Z',
  },
  latest_task: null,
  has_annotations: false,
}

beforeEach(() => {
  vi.restoreAllMocks()
  routerPush.mockReset()
})
afterEach(() => {
  vi.useRealTimers()
  document.body.innerHTML = ''
})

function mountView(role: 'owner' | 'editor' | 'viewer' = 'viewer') {
  return mount(ProjectVideosView, {
    props: { project: { ...project, role } },
    global: {
      plugins: [ElementPlus],
      stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } },
    },
  })
}

describe('ProjectVideosView', () => {
  it('lets a viewer inspect and play ready videos without write controls', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            path.includes('/videos?')
              ? { items: [video], page: 1, page_size: 50, total: 1 }
              : project,
        }),
      ),
    )
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('camera-01')
    expect(wrapper.text()).toContain('7K3M9Q2X')
    expect(wrapper.text()).not.toContain(video.id.slice(0, 8))
    expect(wrapper.text()).toContain('01:05')
    expect(wrapper.text()).toContain('48/50')
    expect(wrapper.text()).toContain('已采样')
    expect(wrapper.text()).toContain('已筛帧')
    expect(wrapper.text()).toContain('48/50 帧启用')
    expect(wrapper.find('[data-test="import-videos"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="export-dataset"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="enabled-video-id"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="configure-video-id"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="frames-video-id"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="frames-video-id"]').text()).toBe('筛帧')
    expect(wrapper.get('[data-test="annotate-video-id"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="download-video-id"]').exists()).toBe(false)

    await wrapper.get('[data-test="play-video-id"]').trigger('click')
    await flushPromises()
    expect(new DOMWrapper(document.body).get('video').attributes('src')).toBe(
      '/api/v1/projects/project-id/videos/video-id/content',
    )
  })

  it('shows the import entry to owners and editors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            path.includes('/videos?')
              ? { items: [video], page: 1, page_size: 50, total: 1 }
              : { ...project, role: 'editor' },
        }),
      ),
    )
    const wrapper = mountView('editor')
    await flushPromises()

    expect(wrapper.find('[data-test="import-videos"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="export-dataset"]').exists()).toBe(true)
    const toolbarActions = wrapper.get('[data-test="video-toolbar-actions"]')
    expect(toolbarActions.find('[data-test="import-videos"]').exists()).toBe(true)
    expect(toolbarActions.find('[data-test="export-dataset"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="select-video-id"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="configure-video-id"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="extract-video-id"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="annotate-video-id"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[data-test="annotate-video-id"]').trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/projects/project-id/videos/video-id/annotation')
  })

  it('selects the current page and requests the explicit all page size', async () => {
    const second = { ...video, id: 'video-two', title: 'camera-02' }
    const fetchMock = vi.fn().mockImplementation((path: string) => {
      const pageSize = path.includes('/videos?')
        ? Number(new URL(path, 'http://test').searchParams.get('page_size'))
        : 50
      return Promise.resolve({
        ok: true,
        json: async () =>
          path.includes('/videos?')
            ? { items: [video, second], page: 1, page_size: pageSize, total: 2 }
            : { ...project, role: 'editor' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountView('editor')
    await flushPromises()

    const actionLane = wrapper.get('[data-test="video-action-lane"]').element
    await wrapper.get('[data-test="select-video-id"] input').setValue(true)
    expect(wrapper.get('[data-test="video-action-lane"]').element).toBe(actionLane)
    expect(
      wrapper.get('[data-test="select-all"] .el-checkbox__input').classes(),
    ).toContain('is-indeterminate')
    expect(wrapper.text()).toContain('已选择 1 个视频')

    await wrapper.get('[data-test="select-all"] input').setValue(true)
    expect(wrapper.text()).toContain('已选择 2 个视频')

    await wrapper.get('[data-test="page-size"]').setValue('999')
    await flushPromises()
    expect(
      fetchMock.mock.calls.some(([path]) =>
        String(path).includes('/videos?page=1&page_size=999'),
      ),
    ).toBe(true)
    expect(wrapper.find('option[value="999"]').text()).toBe('全部')
    // 视频总数只在 header 副信息里出现一次；页内工具行放本页动作，不再重复统计
    expect(wrapper.get('[data-test="page-stat"]').text()).toContain('2 个视频')
    expect(wrapper.get('[data-test="video-action-lane"]').text()).not.toContain('2 个视频')
    expect(wrapper.get('[data-test="video-toolbar-actions"]').text()).toContain('导入视频')
  })

  it('disables importing at 999 videos', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            path.includes('/videos?')
              ? { items: [video], page: 1, page_size: 50, total: 999 }
              : { ...project, role: 'owner' },
        }),
      ),
    )
    const wrapper = mountView('owner')
    await flushPromises()

    expect(wrapper.text()).toContain('999 个视频')
    expect(wrapper.get('[data-test="import-videos"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="import-videos"]').attributes('title')).toContain('999')
  })

  it('keeps media and sampling controls available when a video is disabled', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            path.includes('/videos?')
              ? { items: [{ ...video, enabled: false }], page: 1, page_size: 50, total: 1 }
              : { ...project, role: 'editor' },
        }),
      ),
    )
    const wrapper = mountView('editor')
    await flushPromises()

    expect(wrapper.text()).toContain('视频停用')
    for (const action of ['play', 'configure', 'extract', 'annotate', 'frames']) {
      expect(wrapper.get(`[data-test="${action}-video-id"]`).attributes('disabled')).toBeUndefined()
    }
  })

  it('updates the video switch with the current version', async () => {
    const fetchMock = vi.fn().mockImplementation((path: string, init?: RequestInit) =>
      Promise.resolve({
        ok: true,
        json: async () => {
          if (path.endsWith('/enabled')) return { ...video, enabled: false, version: 3 }
          return path.includes('/videos?')
            ? { items: [video], page: 1, page_size: 50, total: 1 }
            : { ...project, role: 'editor' }
        },
        init,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountView('editor')
    await flushPromises()

    await wrapper.get('[data-test="enabled-video-id"] input').setValue(false)
    await flushPromises()

    const call = fetchMock.mock.calls.find(([path]) => String(path).endsWith('/enabled'))
    expect(call?.[1]?.method).toBe('PUT')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ enabled: false, version: 2 })
  })

  it('summarizes selected risk and splits configured videos from safe batch configuration', async () => {
    const unconfigured = { ...video, id: 'video-new', sampling: null }
    const protectedVideo = { ...video, id: 'video-protected', has_annotations: true }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) => Promise.resolve({
        ok: true,
        json: async () => path.includes('/videos?')
          ? { items: [unconfigured, protectedVideo], page: 1, page_size: 50, total: 2 }
          : { ...project, role: 'editor' },
      })),
    )
    const wrapper = mountView('editor')
    await flushPromises()

    await wrapper.get('[data-test="select-all"] input').setValue(true)
    expect(wrapper.get('[data-test="video-action-lane"]').text()).toContain(
      '已配置 1 · 已抽帧 1 · 已筛帧 1 · 有标注 1',
    )
    await wrapper.get('[data-test="batch-configure"]').trigger('click')
    await flushPromises()
    const body = new DOMWrapper(document.body)
    expect(body.get('[data-test="configure-unconfigured"]').text()).toContain('1 个未配置视频')
    expect(body.get('[data-test="configure-all"]').text()).toContain('全部 2 个视频')
  })

  it('offers unextracted-only processing before destructive batch extraction', async () => {
    const configured = {
      ...video,
      id: 'video-configured',
      sampling: {
        ...video.sampling,
        state: 'configured' as const,
        extracted_frames: 0,
        enabled_frames: 0,
        applied_version: 0,
        frame_revision: 0,
      },
    }
    const protectedVideo = { ...video, id: 'video-protected', has_annotations: true }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) => Promise.resolve({
        ok: true,
        json: async () => path.includes('/videos?')
          ? { items: [configured, protectedVideo], page: 1, page_size: 50, total: 2 }
          : { ...project, role: 'editor' },
      })),
    )
    const wrapper = mountView('editor')
    await flushPromises()

    await wrapper.get('[data-test="select-all"] input').setValue(true)
    await wrapper.get('[data-test="batch-extract"]').trigger('click')
    await flushPromises()
    const body = new DOMWrapper(document.body)
    expect(body.get('[data-test="extract-unextracted"]').text()).toContain('1 个未抽帧视频')
    expect(body.get('[data-test="extract-all"]').text()).toContain('全部 2 个视频')
  })

  it('chooses the batch annotation range before showing model settings', async () => {
    const unannotated = { ...video, id: 'video-new', has_annotations: false }
    const annotated = { ...video, id: 'video-old', has_annotations: true }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((path: string) => Promise.resolve({
        ok: true,
        json: async () => path.includes('/videos?')
          ? { items: [unannotated, annotated], page: 1, page_size: 50, total: 2 }
          : { ...project, role: 'editor' },
      })),
    )
    const wrapper = mountView('editor')
    await flushPromises()

    await wrapper.get('[data-test="select-all"] input').setValue(true)
    await wrapper.get('[data-test="batch-auto-annotate"]').trigger('click')
    await flushPromises()
    const body = new DOMWrapper(document.body)
    expect(body.get('[data-test="annotation-unannotated-only"]').text()).toContain('1 个未标注视频')
    expect(body.get('[data-test="annotation-all"]').text()).toContain('全部 2 个视频')
    expect(body.get('[data-test="annotation-all"]').classes()).toContain('vdw-btn--danger')
  })

  it('separates annotation and screening counts before countdown confirmation', async () => {
    vi.useFakeTimers()
    const annotatedUnscreened = {
      ...video, id: 'annotated-new', has_annotations: true,
      sampling: { ...video.sampling, frame_revision: 1 },
    }
    const annotatedScreened = { ...video, id: 'annotated-old', has_annotations: true }
    const emptyUnscreened = {
      ...video, id: 'empty-new', has_annotations: false,
      sampling: { ...video.sampling, frame_revision: 1 },
    }
    const emptyScreened = { ...video, id: 'empty-old', has_annotations: false }
    const fetchMock = vi.fn().mockImplementation((path: string, init?: RequestInit) => Promise.resolve({
      ok: true,
      json: async () => path.includes('/batch-enabled-by-annotation')
        ? {
            accepted: [
              { video_id: 'annotated-new', sampling: annotatedUnscreened.sampling },
              { video_id: 'annotated-old', sampling: annotatedScreened.sampling },
            ],
            rejected: [
              { input: 'empty-new', reason: 'video has no annotations', code: 'no_annotations' },
              { input: 'empty-old', reason: 'video has no annotations', code: 'no_annotations' },
            ],
          }
        : path.includes('/videos?')
          ? { items: [annotatedUnscreened, annotatedScreened, emptyUnscreened, emptyScreened], page: 1, page_size: 50, total: 4 }
          : { ...project, role: 'editor' },
      init,
    }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountView('editor')
    await flushPromises()

    await wrapper.get('[data-test="select-all"] input').setValue(true)
    await wrapper.get('[data-test="batch-enabled-by-annotation"]').trigger('click')
    await flushPromises()
    let body = new DOMWrapper(document.body)
    expect(body.text()).toContain('1有标注 · 未筛帧')
    expect(body.text()).toContain('1有标注 · 已筛帧')
    expect(body.text()).toContain('1无标注 · 未筛帧')
    expect(body.text()).toContain('1无标注 · 已筛帧')
    expect(body.get('[data-test="enabled-by-annotation-unscreened"]').text()).toContain('1 个未筛帧视频')

    await body.get('[data-test="enabled-by-annotation-all"]').trigger('click')
    await flushPromises()
    body = new DOMWrapper(document.body)
    const confirm = body.get('[data-test="enabled-by-annotation-confirm"]')
    expect(confirm.text()).toContain('3 秒')
    expect(confirm.attributes('disabled')).toBeDefined()
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(confirm.attributes('disabled')).toBeUndefined()

    await confirm.trigger('click')
    await flushPromises()
    const request = fetchMock.mock.calls.find(([path]) => String(path).includes('/batch-enabled-by-annotation'))
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({ scope: 'all', confirm_all: true })
  })
})
