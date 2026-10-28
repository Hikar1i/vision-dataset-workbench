import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { ImageAsset } from '../api/images'
import ImagePreviewDialog from './ImagePreviewDialog.vue'
import VButton from '../ui/VButton.vue'

const image: ImageAsset = { id: 'image-a', directory_id: 'test', file_name: 'a.jpg', source_relative_path: 'test/a.jpg', width: 640, height: 480, file_size: 1024, content_sha256: 'a', materialization: 'copy', enabled: true, annotation_status: 'labeled', annotation_revision: 3, version: 2, annotations: [{ id: 'box', label_id: 'helmet', x_min: 10.1, y_min: 20.2, x_max: 10.4, y_max: 20.6, source: 'import', confidence: null }], created_at: '', updated_at: '' }
const wrappers: ReturnType<typeof mount>[] = []
let resized: ResizeObserverCallback
const disconnect = vi.fn(), observe = vi.fn()
let rect = { x: 0, y: 0, left: 0, top: 0, right: 1000, bottom: 800, width: 1000, height: 800, toJSON() {} }
beforeEach(() => {
  rect = { ...rect, width: 1000, height: 800 }
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => rect)
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: ResizeObserverCallback) { resized = callback }
    disconnect = disconnect
    observe = observe
  })
})
afterEach(() => {
  wrappers.splice(0).forEach(w => w.unmount())
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks()
})
const DialogStub = {
  props: { modelValue: Boolean, fullscreen: Boolean, destroyOnClose: Boolean, closeOnClickModal: Boolean },
  template: '<div v-if="modelValue"><slot name="header" titleId="preview-title"/><slot/></div>',
}
function open(props: Partial<InstanceType<typeof ImagePreviewDialog>['$props']> = {}) {
  const w = mount(ImagePreviewDialog, {
    attachTo: document.body,
    props: { modelValue: true, projectId: 'project-id', image, directoryName: 'test', labelColors: { helmet: '#16866f' }, canEdit: true, locked: false, ...props },
    global: { plugins: [ElementPlus], stubs: { ElDialog: DialogStub } },
  })
  wrappers.push(w); return w
}
function button(w: ReturnType<typeof open>, text: string) {
  return w.findAllComponents(VButton).find(b => b.text().includes(text))!
}
function key(value: string, target: EventTarget = window, extra: KeyboardEventInit = {}) {
  target.dispatchEvent(new KeyboardEvent('keydown', { key: value, bubbles: true, cancelable: true, ...extra }))
}
async function loaded(w: ReturnType<typeof open>) { await w.get('[data-test="preview-image"] image').trigger('load') }
function pointer(w: ReturnType<typeof open>, type: string, x: number, y: number, pointerId = 1) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.assign(event, { button: 0, clientX: x, clientY: y, pointerId })
  w.get('[data-test="preview-stage"]').element.dispatchEvent(event)
}

it('uses a fullscreen modal and continuous-coordinate SVG boxes without changing annotations', async () => {
  const w = open(); await flushPromises()
  expect(w.getComponent(DialogStub).props()).toMatchObject({ fullscreen: true, destroyOnClose: true, closeOnClickModal: false })
  expect(w.get('[data-test="preview-image"] image').attributes('href')).toBe('/api/v1/projects/project-id/images/image-a/file')
  expect(Number(w.get('.preview-annotation-box').attributes('width'))).toBeCloseTo(.3)
  expect(Number(w.get('.preview-annotation-box').attributes('height'))).toBeCloseTo(.4)
  expect(w.get('.preview-annotation-box').attributes('stroke')).toBe('#16866f')
  expect(w.get('.annotation-layer text').text()).toBe('目标 1')
  expect(w.text()).toContain('正在加载图片')
  await loaded(w)
  expect(w.text()).not.toContain('正在加载图片')
  await button(w, '隐藏标注框').trigger('click')
  expect(w.find('.annotation-layer').exists()).toBe(false)
  expect(image.annotations).toHaveLength(1)
  await button(w, '显示标注框').trigger('click')
  expect(w.findAll('.preview-annotation-box')).toHaveLength(1)
})
it('keeps file metadata and position without inventing a video timestamp', () => {
  const w = open({ positionLabel: '5 / 20' })
  for (const text of ['a.jpg', 'test/a.jpg', '640 × 480', '1.0 KB', '1 类 · 1 目标', 'copy', '5 / 20']) expect(w.text()).toContain(text)
  expect(w.find('.timestamp').exists()).toBe(false)
  expect(w.get('.preview-sidebar').findAll('section').map(s => s.classes()[0])).toEqual(['preview-metadata', 'preview-minimap'])
})
it('uses optional category names without requesting labels', () => {
  const w = open({ labelNames: { helmet: 'helmet' } })
  expect(w.get('.annotation-layer text').text()).toBe('helmet #1')
})
it('preserves enabled and annotate events without closing the preview', async () => {
  const w = open()
  await button(w, '打开标注工作台').trigger('click')
  await w.get('[data-test="preview-toggle-enabled"]').trigger('click')
  expect(w.emitted('annotate')?.[0]).toEqual([image])
  key('w', window, { repeat: true }); key('w', window, { ctrlKey: true })
  expect(w.emitted('annotate')).toHaveLength(1)
  key('w'); expect(w.emitted('annotate')).toHaveLength(2)
  expect(w.emitted('enabled')?.[0]).toEqual([image, false])
  expect(w.emitted('update:modelValue')).toBeUndefined()
  await w.setProps({ image: { ...image, enabled: false } })
  await w.get('[data-test="preview-toggle-enabled"]').trigger('click')
  expect(w.emitted('enabled')?.[1]?.[1]).toBe(true)
  expect(w.text()).toContain('已停用')
})
it('keeps navigation disabled by default and delegates allowed offsets to the parent', async () => {
  const w = open()
  expect(w.get('[data-test="preview-previous"]').attributes('disabled')).toBeDefined()
  expect(w.get('[data-test="preview-next"]').attributes('disabled')).toBeDefined()
  key('a'); key('d'); expect(w.emitted('navigate')).toBeUndefined()
  await w.setProps({ previousDisabled: false, nextDisabled: false })
  await w.get('[data-test="preview-previous"]').trigger('click'); key('d')
  expect(w.emitted('navigate')).toEqual([[-1], [1]])
  expect(w.emitted('update:modelValue')).toBeUndefined()
})
it.each([{ canEdit: false }, { locked: true }, { navigating: true }])('blocks writes for %o including keyboard while preserving inspection', async props => {
  const w = open({ ...props, nextDisabled: false, previousDisabled: false })
  expect(w.get('[data-test="preview-toggle-enabled"]').attributes('disabled')).toBeDefined()
  expect(button(w, '打开标注工作台').props('disabled')).toBe(true)
  key('s'); expect(w.emitted('enabled')).toBeUndefined()
  key('w'); expect(w.emitted('annotate')).toBeUndefined()
  key('h'); await flushPromises(); expect(w.find('.annotation-layer').exists()).toBe(false)
  if ('navigating' in props) {
    key('a'); key('d')
    expect(w.get('[data-test="preview-next"]').attributes('disabled')).toBeDefined()
    expect(w.emitted('navigate')).toBeUndefined()
    expect(w.text()).toContain('正在切换图片')
  }
})
it('omits the annotation action for screening drafts and explains empty labels', () => {
  const w = open({ showAnnotationAction: false, image: { ...image, annotations: [] } })
  expect(button(w, '打开标注工作台')).toBeUndefined()
  key('w'); expect(w.emitted('annotate')).toBeUndefined()
  expect(w.find('[data-test="preview-toggle-enabled"]').exists()).toBe(true)
  expect(w.text()).toContain('无目标框')
})
it('recovers from load errors by retrying and selecting another image', async () => {
  const w = open()
  await w.get('[data-test="preview-image"] image').trigger('error')
  expect(w.get('[role="alert"]').text()).toContain('图片加载失败')
  expect(w.find('.annotation-layer').exists()).toBe(false)
  await button(w, '重新加载图片').trigger('click')
  expect(w.get('[data-test="preview-image"] image').attributes('href')).toContain('?preview_retry=1')
  expect(w.find('[role="alert"]').exists()).toBe(false)
  await loaded(w); expect(w.text()).not.toContain('正在加载图片')
  await w.get('[data-test="preview-image"] image').trigger('error')
  await w.setProps({ image: { ...image, id: 'image-b' } })
  expect(w.find('[role="alert"]').exists()).toBe(false)
  expect(w.get('[data-test="preview-image"] image').attributes('href')).toBe('/api/v1/projects/project-id/images/image-b/file')
})
it('aligns the minimap while zooming, panning, resizing and resetting on image changes', async () => {
  const w = open(); await flushPromises(); await loaded(w)
  const main = () => w.get('[data-test="preview-image"]')
  const viewport = () => w.get('.preview-viewport-box')
  const initial = main().attributes('style')
  expect(Number(viewport().attributes('width'))).toBe(640)
  for (let i = 0; i < 5; i++) await w.get('[data-test="preview-zoom-in"]').trigger('click')
  expect(w.get('[data-test="preview-zoom"]').text()).toBe('150%')
  expect(main().attributes('style')).not.toBe(initial)
  expect(Number(viewport().attributes('width'))).toBeLessThan(640)
  const before = viewport().attributes('x')
  pointer(w, 'pointerdown', 400, 400); pointer(w, 'pointermove', 300, 400, 2)
  await flushPromises(); expect(viewport().attributes('x')).toBe(before)
  pointer(w, 'pointermove', 300, 400)
  await flushPromises(); expect(Number(viewport().attributes('x'))).toBeGreaterThan(Number(before))
  pointer(w, 'pointerup', 300, 400); await flushPromises()
  expect(w.get('[data-test="preview-stage"]').classes()).not.toContain('dragging')
  rect = { ...rect, width: 1200, height: 900 }; resized([], {} as ResizeObserver)
  await flushPromises()
  expect(Number(viewport().attributes('width'))).toBeGreaterThan(0)
  expect(Number(viewport().attributes('x')) + Number(viewport().attributes('width'))).toBeLessThanOrEqual(640)
  await w.setProps({ image: { ...image, id: 'image-b', width: 320, height: 640 } })
  expect(w.get('[data-test="preview-zoom"]').text()).toBe('100%')
  expect(Number(viewport().attributes('width'))).toBe(320)
  expect(Number(viewport().attributes('height'))).toBe(640)
  expect(w.get('.preview-minimap svg').attributes('viewBox')).toBe('0 0 320 640')
  expect(observe).toHaveBeenCalled()
  w.unmount(); expect(disconnect).toHaveBeenCalled()
})
it('uses Ctrl+wheel around the pointer, caps zoom and restores fit with R', async () => {
  const w = open(); await flushPromises()
  const stage = w.get('[data-test="preview-stage"]')
  await stage.trigger('wheel', { deltaY: -1 })
  expect(w.get('[data-test="preview-zoom"]').text()).toBe('100%')
  stage.element.dispatchEvent(new WheelEvent('wheel', { deltaY: -1, ctrlKey: true, clientX: 500, clientY: 400, cancelable: true }))
  await flushPromises()
  expect(w.get('[data-test="preview-zoom"]').text()).toBe('110%')
  for (let i = 0; i < 45; i++) await w.get('[data-test="preview-zoom-in"]').trigger('click')
  expect(w.get('[data-test="preview-zoom"]').text()).toBe('500%')
  expect(w.get('[data-test="preview-zoom-in"]').attributes('disabled')).toBeDefined()
  key('r'); await flushPromises(); expect(w.get('[data-test="preview-zoom"]').text()).toBe('100%')
})
it('protects input, composition and modified shortcuts and avoids repeated writes', async () => {
  const w = open({ nextDisabled: false })
  const input = document.createElement('input'); w.element.appendChild(input)
  key('d', input); key('s', input); key('h', input)
  key('s', window, { ctrlKey: true }); key('s', window, { metaKey: true }); key('s', window, { isComposing: true }); key('s', window, { repeat: true })
  expect(w.emitted('navigate')).toBeUndefined(); expect(w.emitted('enabled')).toBeUndefined()
  key('s'); expect(w.emitted('enabled')).toEqual([[image, false]])
  await w.setProps({ modelValue: false }); key('s'); key('d')
  expect(w.emitted('enabled')).toHaveLength(1); expect(w.emitted('navigate')).toBeUndefined()
})
it('supports the modal close contract and a visible empty state', async () => {
  const w = open({ image: null })
  expect(w.text()).toContain('未选择图片')
  await w.get('[aria-label="关闭图片预览"]').trigger('click')
  expect(w.emitted('update:modelValue')).toEqual([[false]])
  w.getComponent(DialogStub).vm.$emit('update:modelValue', false)
  expect(w.emitted('update:modelValue')).toHaveLength(2)
})
