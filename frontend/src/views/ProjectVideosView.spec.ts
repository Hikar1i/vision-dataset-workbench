import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProjectVideosView from './ProjectVideosView.vue'

vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: 'project-id' } }) }))

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
  version: 2,
  created_at: '2026-07-23T01:00:00Z',
  updated_at: '2026-07-23T01:00:00Z',
  sampling: {
    id: 'plan-id', state: 'sampled', mode: 'target_frames', parameters: { minimum: 50, maximum: 200 },
    output_format: 'jpg', output_quality: 2, computed_interval: null, expected_frames: 50,
    extracted_frames: 50, enabled_frames: 48, version: 1, applied_version: 1,
    generation: 1, frame_revision: 2,
  },
}

beforeEach(() => vi.restoreAllMocks())

function mountView() {
  return mount(ProjectVideosView, {
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
    expect(wrapper.text()).toContain('01:05')
    expect(wrapper.find('[data-test="import-videos"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="configure-video-id"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="frames-video-id"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="download-video-id"]').exists()).toBe(false)

    await wrapper.get('[data-test="play-video-id"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('video').attributes('src')).toBe(
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
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.find('[data-test="import-videos"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="select-video-id"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="configure-video-id"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="extract-video-id"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="settings-link"]').attributes('href')).toBe(
      '/projects/project-id/settings',
    )
  })
})
