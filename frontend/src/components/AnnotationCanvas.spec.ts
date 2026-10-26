import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { FrameAnnotation } from '../api/annotations'
import AnnotationCanvas from './AnnotationCanvas.vue'

const transformerNodes = vi.fn()
const stageFindOne = vi.fn()
const VRectStub = defineComponent({
  props: ['config'],
  emits: ['mousedown', 'mouseenter', 'mouseleave', 'dragend', 'transformend', 'contextmenu'],
  template: '<div class="rect-stub" />',
})
const VTextStub = defineComponent({
  props: ['config'],
  template: '<span class="text-stub">{{ config.text }}</span>',
})
const SlotStub = defineComponent({ template: '<div><slot /></div>' })
const VStageStub = defineComponent({
  props: ['config'],
  emits: ['mousedown', 'mousemove', 'mouseup', 'mouseleave', 'wheel'],
  setup(_props, { expose }) {
    expose({ getNode: () => ({ findOne: stageFindOne }) })
  },
  template: '<div class="stage-stub"><slot /></div>',
})
const VGroupStub = defineComponent({
  props: ['config'],
  template: '<div class="group-stub"><slot /></div>',
})
const VTransformerStub = defineComponent({
  props: ['config'],
  setup(_props, { expose }) {
    expose({
      getNode: () => ({
        nodes: transformerNodes,
        getLayer: () => ({ batchDraw: () => undefined }),
      }),
    })
  },
  template: '<div class="transformer-stub" />',
})
const stubs = {
  'v-stage': VStageStub,
  'v-layer': SlotStub,
  'v-group': VGroupStub,
  'v-image': defineComponent({ name: 'VImage', props: ['config'], template: '<div class="image-stub"/>' }),
  'v-rect': VRectStub,
  'v-text': VTextStub,
  'v-transformer': VTransformerStub,
  'v-line': true,
}
const annotations: FrameAnnotation[] = [
  {
    id: 'helmet-box',
    label_id: 'helmet',
    x_min: 10,
    y_min: 20,
    x_max: 110,
    y_max: 220,
    source: 'manual',
    confidence: null,
  },
  {
    id: 'person-box',
    label_id: 'person',
    x_min: 200,
    y_min: 100,
    x_max: 300,
    y_max: 400,
    source: 'model',
    confidence: 0.9,
  },
]

beforeEach(() => {
  transformerNodes.mockClear(); stageFindOne.mockReset().mockReturnValue(null)
  vi.stubGlobal('Image', class {
    constructor() {
      const img = document.createElement('img')
      Object.defineProperty(img, 'src', { set: () => img.dispatchEvent(new Event('load')) })
      return img
    }
  })
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    },
  )
})

describe('AnnotationCanvas', () => {
  function pointerFixture() {
    const point = { x: 0.2, y: 0.3 }
    const stage = { getPointerPosition: () => ({ ...point }) }
    const event = (button = 0) => ({
      target: { getStage: () => stage },
      evt: { button },
    })
    return { point, event }
  }

  it('omits hidden categories and disables box editing when read only', async () => {
    const wrapper = mount(AnnotationCanvas, {
      props: {
        imageUrl: '/frame.jpg',
        imageWidth: 1920,
        imageHeight: 1080,
        annotations,
        labels: [
          { id: 'helmet', name: 'helmet', color: '#16866f' },
          { id: 'person', name: 'person', color: '#e85d4a' },
        ],
        selectedId: 'helmet-box',
        mode: 'select',
        readonly: true,
        hiddenLabelIds: ['person'],
      },
      global: { stubs },
    })

    const boxes = wrapper.findAllComponents(VRectStub).filter(
      (item) => String(item.props('config').name ?? '').startsWith('annotation-'),
    )
    expect(boxes).toHaveLength(1)
    expect(boxes[0]!.props('config')).toMatchObject({
      name: 'annotation-helmet-box',
      draggable: false,
      stroke: '#16866f',
    })
    expect(wrapper.findComponent(VTransformerStub).exists()).toBe(false)

    boxes[0]!.vm.$emit('transformend', { target: {} })
    boxes[0]!.vm.$emit('dragend', { target: {} })
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('change')).toBeUndefined()
  })

  it('renders global labels, selected fill, pending bounds and blocks context menus', async () => {
    const wrapper = mount(AnnotationCanvas, {
      props: {
        imageUrl: '/frame.jpg',
        imageWidth: 1920,
        imageHeight: 1080,
        annotations,
        labels: [
          { id: 'helmet', name: 'helmet', color: '#16866f' },
          { id: 'person', name: 'person', color: '#e85d4a' },
        ],
        selectedId: 'person-box',
        mode: 'select',
        pendingBounds: { x_min: 400, y_min: 200, x_max: 600, y_max: 500 },
      },
      global: { stubs },
    })

    const boxes = wrapper.findAllComponents(VRectStub)
    const person = boxes.find((item) => item.props('config').name === 'annotation-person-box')
    expect(person?.props('config')).toMatchObject({
      fill: 'rgb(232 93 74 / 0.28)',
      strokeWidth: 3,
    })
    const labels = wrapper.findAllComponents(VTextStub)
    expect(labels.map((item) => item.text())).toEqual([
      'helmet #1',
      'person #2 · 0.90',
    ])
    expect(labels.every((item) => item.props('config').fontSize === 17)).toBe(true)
    const labelGroups = wrapper.findAllComponents(VGroupStub).filter(
      (item) => item.props('config')?.listening === false && item.props('config')?.x !== undefined,
    )
    expect(labelGroups.map((item) => item.props('config').y)).toEqual([-6, 74])
    expect(boxes.some((item) => item.props('config').dash?.length)).toBe(true)
    expect(wrapper.getComponent(VTransformerStub).props('config')).toMatchObject({
      keepRatio: false,
      shiftBehavior: 'default',
      centeredScaling: false,
      borderStroke: '#3bb8d8',
      anchorStroke: '#141f25',
      anchorFill: '#3bb8d8',
      enabledAnchors: [
        'top-left',
        'top-right',
        'bottom-right',
        'bottom-left',
      ],
    })

    const event = new Event('contextmenu', { cancelable: true })
    wrapper.get('[data-test="annotation-canvas"]').element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('hides annotation titles in dense mode', () => {
    const wrapper = mount(AnnotationCanvas, {
      props: {
        imageUrl: '/frame.jpg',
        imageWidth: 1920,
        imageHeight: 1080,
        annotations,
        labels: [
          { id: 'helmet', name: 'helmet', color: '#16866f' },
          { id: 'person', name: 'person', color: '#e85d4a' },
        ],
        selectedId: null,
        mode: 'select',
        dense: true,
      },
      global: { stubs },
    })

    expect(wrapper.findAllComponents(VTextStub)).toHaveLength(0)
    expect(wrapper.findAllComponents(VRectStub).filter(
      (item) => String(item.props('config').name ?? '').startsWith('annotation-'),
    )).toHaveLength(2)
  })

  it('reports a selected annotation and pointer anchor on right click', () => {
    const wrapper = mount(AnnotationCanvas, {
      props: {
        imageUrl: '/frame.jpg',
        imageWidth: 1920,
        imageHeight: 1080,
        annotations,
        labels: [],
        selectedId: null,
        mode: 'select',
      },
      global: { stubs },
    })
    const preventDefault = vi.fn()
    const box = wrapper.findAllComponents(VRectStub).find(
      (item) => item.props('config').name === 'annotation-helmet-box',
    )!

    box.vm.$emit('contextmenu', {
      cancelBubble: false,
      target: {
        getStage: () => ({ getPointerPosition: () => ({ x: 50, y: 60 }) }),
      },
      evt: { preventDefault },
    })

    expect(preventDefault).toHaveBeenCalledOnce()
    expect(wrapper.emitted('select')).toEqual([['helmet-box']])
    expect(wrapper.emitted('context')).toEqual([['helmet-box', { x: 50, y: 60 }]])
  })

  it('completes the default drawing gesture on the second click', async () => {
    const wrapper = mount(AnnotationCanvas, {
      props: {
        imageUrl: '/frame.jpg',
        imageWidth: 1920,
        imageHeight: 1080,
        annotations,
        labels: [],
        selectedId: null,
        mode: 'draw',
      },
      global: { stubs },
    })
    const stage = wrapper.findComponent(VStageStub)
    const pointer = pointerFixture()

    stage.vm.$emit('mousedown', pointer.event())
    pointer.point.x = 0.8
    pointer.point.y = 0.7
    stage.vm.$emit('mousemove', pointer.event())
    stage.vm.$emit('mouseup', pointer.event())
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('request-category')).toBeUndefined()
    const preview = wrapper.findAllComponents(VRectStub).find(
      (item) => item.props('config').dash?.length,
    )
    expect(preview?.props('config')).toMatchObject({
      width: expect.any(Number),
      height: expect.any(Number),
      listening: false,
    })

    stage.vm.$emit('mousedown', pointer.event())
    await wrapper.vm.$nextTick()

    const request = wrapper.emitted('request-category')
    expect(request).toHaveLength(1)
    expect(request?.[0]?.[0]).toMatchObject({
      x_min: expect.any(Number),
      y_min: expect.any(Number),
      x_max: expect.any(Number),
      y_max: expect.any(Number),
    })
    expect(request?.[0]?.[1]).toEqual({ x: 0.8, y: 0.7 })
  })

  it('completes drag drawing on mouseup and ignores non-left buttons', async () => {
    const wrapper = mount(AnnotationCanvas, {
      props: {
        imageUrl: '/frame.jpg',
        imageWidth: 1920,
        imageHeight: 1080,
        annotations,
        labels: [],
        selectedId: null,
        mode: 'draw',
        dragToDraw: true,
      },
      global: { stubs },
    })
    const stage = wrapper.findComponent(VStageStub)
    const pointer = pointerFixture()

    stage.vm.$emit('mousedown', pointer.event(2))
    pointer.point.x = 0.8
    pointer.point.y = 0.7
    stage.vm.$emit('mousemove', pointer.event(2))
    stage.vm.$emit('mouseup', pointer.event(2))
    expect(wrapper.emitted('request-category')).toBeUndefined()

    pointer.point.x = 0.2
    pointer.point.y = 0.3
    stage.vm.$emit('mousedown', pointer.event())
    pointer.point.x = 0.8
    pointer.point.y = 0.7
    stage.vm.$emit('mousemove', pointer.event())
    pointer.point.x = 0.9
    pointer.point.y = 0.75
    stage.vm.$emit('mouseup', pointer.event())
    await wrapper.vm.$nextTick()

    const request = wrapper.emitted('request-category')
    expect(request).toHaveLength(1)
    expect(request?.[0]?.[1]).toEqual({ x: 0.9, y: 0.75 })
  })

  it('clears an unfinished two-click drawing when the tool changes', async () => {
    const wrapper = mount(AnnotationCanvas, {
      props: {
        imageUrl: '/frame.jpg',
        imageWidth: 1920,
        imageHeight: 1080,
        annotations,
        labels: [],
        selectedId: null,
        mode: 'draw',
      },
      global: { stubs },
    })
    const stage = wrapper.findComponent(VStageStub)
    const pointer = pointerFixture()

    stage.vm.$emit('mousedown', pointer.event())
    pointer.point.x = 0.8
    pointer.point.y = 0.7
    stage.vm.$emit('mousemove', pointer.event())
    await wrapper.setProps({ mode: 'select' })
    await wrapper.setProps({ mode: 'draw' })
    stage.vm.$emit('mousedown', pointer.event())
    stage.vm.$emit('mouseup', pointer.event())
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('request-category')).toBeUndefined()
  })

  it('cancels an unfinished drawing and resets frame view with optional zoom preservation', async () => {
    const wrapper = mount(AnnotationCanvas, {
      props: {
        imageUrl: '/frame.jpg',
        imageWidth: 1920,
        imageHeight: 1080,
        annotations: [],
        labels: [],
        selectedId: null,
        mode: 'draw',
      },
      global: { stubs },
    })
    const stage = wrapper.findComponent(VStageStub)
    const pointer = pointerFixture()

    stage.vm.$emit('mousedown', pointer.event())
    pointer.point.x = 0.8
    pointer.point.y = 0.7
    stage.vm.$emit('mousemove', pointer.event())
    await wrapper.vm.$nextTick()
    expect(wrapper.findAllComponents(VRectStub).some(
      (item) => item.props('config').dash?.length,
    )).toBe(true)

    const canvas = wrapper.vm as unknown as {
      cancelDrawing: () => boolean
      resetFrameView: (preserveZoom: boolean) => void
      zoomBy: (factor: number) => void
      zoomPercent: number
    }
    expect(canvas.cancelDrawing()).toBe(true)
    await wrapper.vm.$nextTick()
    expect(wrapper.findAllComponents(VRectStub).some(
      (item) => item.props('config').dash?.length,
    )).toBe(false)
    expect(canvas.cancelDrawing()).toBe(false)

    canvas.zoomBy(1.1)
    canvas.resetFrameView(true)
    expect(canvas.zoomPercent).toBe(110)
    canvas.resetFrameView(false)
    expect(canvas.zoomPercent).toBe(100)
  })

  it('lets draw gestures pass through existing annotation boxes', () => {
    const wrapper = mount(AnnotationCanvas, {
      props: {
        imageUrl: '/frame.jpg',
        imageWidth: 1920,
        imageHeight: 1080,
        annotations,
        labels: [],
        selectedId: 'helmet-box',
        mode: 'draw',
      },
      global: { stubs },
    })

    const boxes = wrapper.findAllComponents(VRectStub).filter(
      (item) => String(item.props('config').name ?? '').startsWith('annotation-'),
    )
    expect(boxes).toHaveLength(2)
    expect(boxes.every((item) => item.props('config').listening === false)).toBe(true)
    expect(boxes.every((item) => item.props('config').draggable === false)).toBe(true)
    expect(wrapper.findComponent(VTransformerStub).exists()).toBe(false)
  })
})

it.each(['continuous', 'pixel'] as const)('resizes a small box using %s coordinate rules', async coordinateMode => {
  const imported: FrameAnnotation = { id: 'tiny', label_id: 'helmet', x_min: 10.1, y_min: 20.2, x_max: 10.4, y_max: 20.6, source: 'import', confidence: null }
  const wrapper = mount(AnnotationCanvas, { props: { imageUrl: '/tiny.jpg', imageWidth: 640, imageHeight: 480, annotations: [imported], labels: [], selectedId: 'tiny', mode: 'select', coordinateMode }, global: { stubs } })
  const box = wrapper.findAllComponents(VRectStub).find(item => item.props('config').name === 'annotation-tiny')!
  const scaleX = vi.fn().mockReturnValue(1), scaleY = vi.fn().mockReturnValue(1)
  box.vm.$emit('transformend', { target: { x: () => 10.1, y: () => 20.2, width: () => 0.3, height: () => 0.4, scaleX, scaleY } })
  await wrapper.vm.$nextTick()
  const changed = wrapper.emitted('change')?.[0]?.[0] as FrameAnnotation[]
  expect(changed).toHaveLength(1)
  expect(changed[0]).toMatchObject(coordinateMode === 'continuous'
    ? { x_min: 10.1, y_min: 20.2, x_max: expect.closeTo(10.4), y_max: expect.closeTo(20.6), source: 'manual', confidence: null }
    : { x_min: 10, y_min: 20, x_max: 12, y_max: 22 })
  expect(scaleX).toHaveBeenCalledWith(1); expect(scaleY).toHaveBeenCalledWith(1)
  wrapper.unmount()
})

it('moves imported subpixel boxes without rounding or changing untouched sources', async () => {
  const imported: FrameAnnotation = { ...annotations[0]!, source: 'import', x_min: 10.1, y_min: 20.2, x_max: 10.4, y_max: 20.6 }
  const wrapper = mount(AnnotationCanvas, { props: { imageUrl: '/tiny.jpg', imageWidth: 640, imageHeight: 480, annotations: [imported, annotations[1]!], labels: [], selectedId: imported.id, mode: 'select', coordinateMode: 'continuous' }, global: { stubs } })
  const box = wrapper.findAllComponents(VRectStub).find(item => item.props('config').name === `annotation-${imported.id}`)!
  box.vm.$emit('dragend', { target: { x: () => 30.25, y: () => 40.5 } })
  const changed = wrapper.emitted('change')?.[0]?.[0] as FrameAnnotation[]
  expect(changed[0]?.x_min).toBe(30.25)
  expect(changed[0]!.x_max - changed[0]!.x_min).toBeCloseTo(0.3)
  expect(changed[0]?.source).toBe('manual')
  expect(changed[1]).toEqual(annotations[1])
  wrapper.unmount()
})

afterEach(() => { vi.unstubAllGlobals() })

it('clears the previous image, ignores stale callbacks and exposes a failed-load retry', async () => {
  const requests: HTMLImageElement[] = []
  vi.stubGlobal('Image', class { constructor() { const img = document.createElement('img'); requests.push(img); return img } })
  const wrapper = mount(AnnotationCanvas, { props: { imageUrl: '/a.jpg', imageWidth: 640, imageHeight: 480, annotations: [], labels: [], selectedId: null, mode: 'select' }, global: { stubs } })
  requests[0]!.dispatchEvent(new Event('load')); await wrapper.vm.$nextTick()
  expect(wrapper.getComponent({ name: 'VImage' }).props('config').image).toBe(requests[0])
  await wrapper.setProps({ imageUrl: '/b.jpg' })
  expect(wrapper.getComponent({ name: 'VImage' }).props('config').image).toBeNull()
  expect(wrapper.text()).toContain('正在加载图片')
  await wrapper.setProps({ imageUrl: '/c.jpg' })
  requests[1]!.dispatchEvent(new Event('load')); requests[1]!.dispatchEvent(new Event('error')); await wrapper.vm.$nextTick()
  expect(wrapper.getComponent({ name: 'VImage' }).props('config').image).toBeNull()
  expect(wrapper.text()).not.toContain('图片加载失败')
  requests[2]!.dispatchEvent(new Event('error')); await wrapper.vm.$nextTick()
  expect(wrapper.text()).toContain('图片加载失败')
  await wrapper.get('.canvas-image-state button').trigger('click')
  expect(requests[3]!.src).toContain('/c.jpg')
  requests[3]!.dispatchEvent(new Event('load')); await wrapper.vm.$nextTick()
  expect(wrapper.getComponent({ name: 'VImage' }).props('config').image).toBe(requests[3])
  expect(wrapper.find('.canvas-image-state').exists()).toBe(false)
  wrapper.unmount()
})

it.each(['pixel', 'continuous'] as const)('blocks drawing and geometry changes until %s image loading succeeds', async coordinateMode => {
  const requests: HTMLImageElement[] = []
  vi.stubGlobal('Image', class { constructor() { const img = document.createElement('img'); requests.push(img); return img } })
  const wrapper = mount(AnnotationCanvas, { props: { imageUrl: '/missing.jpg', imageWidth: 640, imageHeight: 480, annotations, labels: [], selectedId: 'helmet-box', mode: 'draw', dragToDraw: true, coordinateMode }, global: { stubs } })
  const stage = wrapper.getComponent(VStageStub)
  let point = { x: 0.2, y: 0.3 }
  const event = { target: { getStage: () => ({ getPointerPosition: () => point }) }, evt: { button: 0 } }
  const gesture = () => { stage.vm.$emit('mousedown', event); point = { x: 0.8, y: 0.7 }; stage.vm.$emit('mousemove', event); stage.vm.$emit('mouseup', event) }
  gesture()
  expect(wrapper.emitted('request-category')).toBeUndefined()
  requests[0]!.dispatchEvent(new Event('error')); await wrapper.setProps({ mode: 'select' })
  const box = wrapper.findAllComponents(VRectStub).find(item => item.props('config').name === 'annotation-helmet-box')!
  expect(box.props('config').draggable).toBe(false)
  expect(wrapper.findComponent(VTransformerStub).exists()).toBe(false)
  box.vm.$emit('dragend', { target: {} }); box.vm.$emit('transformend', { target: {} })
  expect(wrapper.emitted('change')).toBeUndefined()
  await wrapper.get('.canvas-image-state button').trigger('click')
  requests[1]!.dispatchEvent(new Event('load')); await wrapper.setProps({ mode: 'draw' })
  point = { x: 0.2, y: 0.3 }; gesture()
  expect(wrapper.emitted('request-category')).toHaveLength(1)
  await wrapper.setProps({ mode: 'select' })
  expect(wrapper.findComponent(VTransformerStub).exists()).toBe(true)
  wrapper.unmount()
})

it('rebinds the selected transformer when retry loads the image without changing selection', async () => {
  const requests: HTMLImageElement[] = []
  vi.stubGlobal('Image', class { constructor() { const img = document.createElement('img'); requests.push(img); return img } })
  const node = { name: 'selected-box' }
  stageFindOne.mockReturnValue(node)
  const wrapper = mount(AnnotationCanvas, { props: { imageUrl: '/a.jpg', imageWidth: 640, imageHeight: 480, annotations, labels: [], selectedId: 'helmet-box', mode: 'select' }, global: { stubs } })
  requests[0]!.dispatchEvent(new Event('error')); await wrapper.vm.$nextTick()
  await wrapper.get('.canvas-image-state button').trigger('click')
  requests[1]!.dispatchEvent(new Event('load')); await flushPromises()
  expect(stageFindOne).toHaveBeenCalledWith('.annotation-helmet-box')
  expect(transformerNodes).toHaveBeenLastCalledWith([node])
  wrapper.unmount()
})
