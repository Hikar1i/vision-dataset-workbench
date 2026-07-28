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
const stubs = {
  'v-stage': SlotStub,
  'v-layer': SlotStub,
  'v-group': SlotStub,
  'v-image': true,
  'v-rect': VRectStub,
  'v-text': VTextStub,
  'v-transformer': true,
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
    source: 'manual',
    confidence: null,
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
  it('omits hidden categories and disables dragging when read only', () => {
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
      'person #2',
    ])
    expect(labels.every((item) => item.props('config').fontSize === 28)).toBe(true)
    expect(boxes.some((item) => item.props('config').dash?.length)).toBe(true)

    const event = new Event('contextmenu', { cancelable: true })
    wrapper.get('[data-test="annotation-canvas"]').element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })
})
