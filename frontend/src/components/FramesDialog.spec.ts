import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearVideoWorkspaceState } from '../ui/videoWorkspaceState'
import FramesDialog from './FramesDialog.vue'

const sampling = {
  id: 'plan-id', state: 'sampled', mode: 'frame_interval', parameters: {},
  output_format: 'jpg', output_quality: 2, computed_interval: 30,
  expected_frames: 205, extracted_frames: 205, enabled_frames: 204,
  version: 1, applied_version: 1, generation: 1, frame_revision: 1, updated_at: '',
}
const frames = Array.from({ length: 205 }, (_, index) => ({
  id: `frame-${index + 1}`,
  sequence: index + 1,
  source_frame_index: index * 30,
  time_offset: index,
  enabled: index !== 1,
  file_size: 1024,
  created_at: '',
  annotations: index === 0 ? [{
    id: 'preview-box-1', label_id: 'label-id', x_min: 10, y_min: 20, x_max: 110, y_max: 220,
  }] : [],
}))

const response = (value: unknown) => Promise.resolve({ ok: true, json: async () => value })

function fetchMock() {
  return vi.fn((input: string | URL | Request, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'PUT') return response({ ...sampling, frame_revision: 2 })
    if (url.endsWith('/annotation-summary')) {
      return response({ annotated_frame_ids: ['frame-1', 'frame-2', 'frame-3'] })
    }
    if (url.endsWith('/labels')) {
      return response([{ id: 'label-id', name: 'helmet', description_zh: '安全帽', color: '#ffca3a', sort_order: 0, enabled: true, version: 1, created_at: '', updated_at: '' }])
    }
    if (url.endsWith('/annotations')) {
      return response({ frame_id: 'frame-1', annotation_revision: 1, items: [{ id: 'box-1', label_id: 'label-id', x_min: 10, y_min: 20, x_max: 110, y_max: 220, source: 'model', confidence: 0.91 }] })
    }
    const parsed = new URL(url, 'http://localhost')
    const page = Number(parsed.searchParams.get('page') ?? 1)
    const pageSize = Number(parsed.searchParams.get('page_size') ?? 200)
    const start = (page - 1) * pageSize
    return response({ items: frames.slice(start, start + pageSize), page, page_size: pageSize, total: frames.length, sampling })
  })
}

const DialogStub = {
  props: ['modelValue'],
  template: '<section v-if="modelValue"><slot name="header"/><slot/><slot name="footer"/></section>',
}

function mountDialog(canEdit: boolean, fetch = fetchMock()) {
  vi.stubGlobal('fetch', fetch)
  return {
    fetch,
    wrapper: mount(FramesDialog, {
      props: {
        modelValue: true,
        projectId: 'project-id',
        videoId: 'video-id',
        shortCode: 'G989C14B',
        title: 'factory.mp4',
        canEdit,
        imageWidth: 1920,
        imageHeight: 1080,
      },
      global: { plugins: [ElementPlus], stubs: { ElDialog: DialogStub, transition: false } },
    }),
  }
}

beforeEach(clearVideoWorkspaceState)
afterEach(() => vi.unstubAllGlobals())

describe('FramesDialog', () => {
  it('loads all metadata but renders the default page of 100 frames', async () => {
    const { wrapper, fetch } = mountDialog(true)
    await flushPromises()
    expect(wrapper.get('[data-test="frames-brand"]').text()).toBe('VDM / FRAMES')
    expect(fetch.mock.calls.some(([url]) => String(url).includes('include_annotations=true'))).toBe(true)
    expect(wrapper.findAll('[data-test="frame-card"]')).toHaveLength(100)
    expect(wrapper.get('[data-test="total-count"]').text()).toContain('205')
    expect(wrapper.get('[data-test="annotated-count"]').text()).toContain('3')
    expect(wrapper.get('[data-test="annotated-enabled-count"]').text()).toContain('2')
    expect(wrapper.get('[data-test="annotated-disabled-count"]').text()).toContain('1')
    expect(wrapper.get('[data-test="frame-card"] footer span').text())
      .toBe('G989C14B_frame_000001.jpg')
  })

  it('shows thumbnail annotations by default and hides them in memory', async () => {
    const { wrapper } = mountDialog(true)
    await flushPromises()

    expect(wrapper.get('[data-test="thumbnail-annotations-switch"]').classes()).toContain('is-checked')
    expect(wrapper.findAll('[data-test="frame-card"] .annotation-preview rect')).toHaveLength(1)
    await wrapper.get('[data-test="thumbnail-annotations-switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="frame-card"] .annotation-preview').exists()).toBe(false)
  })

  it('applies the thumbnail grid scale after the slider change is committed', async () => {
    const { wrapper } = mountDialog(true)
    await flushPromises()

    expect(wrapper.get('[data-test="grid-scale-value"]').text()).toBe('1.00×')
    expect(wrapper.get('[data-test="frames-grid"]').attributes('style')).toContain('--frame-card-width: 180px')
    const slider = wrapper.getComponent({ name: 'ElSlider' })
    slider.vm.$emit('update:modelValue', 1.5)
    slider.vm.$emit('change', 1.5)
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-test="grid-scale-value"]').text()).toBe('1.50×')
    expect(wrapper.get('[data-test="frames-grid"]').attributes('style')).toContain('--frame-card-width: 270px')

    wrapper.unmount()
    const { wrapper: remounted } = mountDialog(true)
    await flushPromises()
    expect(remounted.get('[data-test="grid-scale-value"]').text()).toBe('1.50×')
    expect(remounted.get('[data-test="frames-grid"]').attributes('style'))
      .toContain('--frame-card-width: 270px')
  })

  it('exposes the active range-selection state', async () => {
    const { wrapper } = mountDialog(true)
    await flushPromises()
    expect(wrapper.get('[data-test="enter-range"]').attributes('aria-pressed')).toBe('false')
    await wrapper.get('[data-test="enter-range"]').trigger('click')
    expect(wrapper.get('[data-test="exit-range"]').attributes('aria-pressed')).toBe('true')
  })

  it('keeps viewer access read-only while allowing large-image inspection', async () => {
    const { wrapper } = mountDialog(false)
    await flushPromises()
    expect(wrapper.find('[data-test="save-changes"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="toggle-frame-1"]').exists()).toBe(false)
    await wrapper.get('[data-test="frame-card"] .frame-thumb').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="frame-preview"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="frame-preview"]').text())
      .toContain('G989C14B_frame_000001.jpg')
    expect(wrapper.find('[data-test="preview-toggle-enabled"]').exists()).toBe(false)
  })

  it('keeps frame changes local until one atomic save', async () => {
    const { wrapper, fetch } = mountDialog(true)
    await flushPromises()
    await wrapper.get('[data-test="toggle-frame-1"]').trigger('click')
    expect(wrapper.get('[data-test="pending-count"]').text()).toContain('1')
    expect(fetch.mock.calls.some((call) => call[1]?.method === 'PUT')).toBe(false)
    await wrapper.get('[data-test="save-changes"]').trigger('click')
    await flushPromises()
    const call = fetch.mock.calls.find((item) => item[1]?.method === 'PUT')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      changes: [{ frame_id: 'frame-1', enabled: false }],
      frame_revision: 1,
    })
    expect(wrapper.get('[data-test="pending-count"]').text()).toContain('0')
  })

  it('uses preview keyboard shortcuts without writing immediately', async () => {
    const { wrapper, fetch } = mountDialog(true)
    await flushPromises()
    await wrapper.get('[data-test="frame-card"] .frame-thumb').trigger('click')
    await flushPromises()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'h' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-test="preview-image"]').classes()).toContain('boxes-hidden')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 's' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-test="pending-count"]').text()).toContain('1')
    expect(fetch.mock.calls.some((call) => call[1]?.method === 'PUT')).toBe(false)
    wrapper.unmount()
  })

  it('renders category boxes and keeps a minimap in sync while zooming and dragging', async () => {
    const { wrapper } = mountDialog(true)
    await flushPromises()
    await wrapper.get('[data-test="frame-card"] .frame-thumb').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="frame-preview"]').text()).toContain('helmet #1 · 0.91')
    expect(wrapper.find('[data-test="preview-minimap"]').exists()).toBe(true)

    const image = wrapper.get('[data-test="preview-image"]')
    const initialTransform = image.attributes('style')
    await wrapper.get('[data-test="preview-zoom-in"]').trigger('click')
    const stage = wrapper.get('[data-test="preview-stage"]')
    stage.element.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, clientX: 100, clientY: 100 }))
    stage.element.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 130, clientY: 120 }))
    stage.element.dispatchEvent(new MouseEvent('pointerup', { bubbles: true, clientX: 130, clientY: 120 }))
    await wrapper.vm.$nextTick()

    expect(image.attributes('style')).not.toBe(initialTransform)
    expect(stage.classes()).toContain('pannable')
  })
})
