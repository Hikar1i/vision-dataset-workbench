import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import type { FrameAnnotation } from '../api/annotations'
import AnnotationCanvas from './AnnotationCanvas.vue'

const VRectStub = defineComponent({
  props: ['config'],
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
    expose({ getNode: () => ({ findOne: () => null }) })
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
        nodes: () => undefined,
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
  'v-image': true,
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

beforeAll(() => {
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
