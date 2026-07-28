import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FrameAnnotationThumbnail from './FrameAnnotationThumbnail.vue'
import { formatFrameTimestamp } from './framePresentation'

describe('FrameAnnotationThumbnail', () => {
  it('keeps annotation coordinates aligned with a contained 16:9 image', async () => {
    const wrapper = mount(FrameAnnotationThumbnail, {
      props: {
        imageUrl: '/frame.jpg',
        imageWidth: 1920,
        imageHeight: 1080,
        sequence: 7,
        timeOffset: 3902.462,
        disabled: false,
        annotations: [{
          id: 'box-1', label_id: 'helmet', x_min: 10, y_min: 20, x_max: 110, y_max: 220,
        }],
        labelColors: { helmet: '#16866f' },
      },
    })

    expect(wrapper.get('svg').attributes('viewBox')).toBe('0 0 1920 1080')
    expect(wrapper.get('rect').attributes()).toMatchObject({
      x: '10', y: '20', width: '100', height: '200', stroke: '#16866f',
    })
    expect(wrapper.get('.timestamp').text()).toBe('65:02.462')
    expect(wrapper.get('.frame-status').text()).toBe('已启用')
    expect(wrapper.get('.sequence').text()).toBe('#7')

    await wrapper.setProps({ disabled: true })
    expect(wrapper.get('.frame-status').text()).toBe('已停用')
    expect(wrapper.classes()).toContain('disabled')
  })

  it('rounds timestamps without rendering an invalid sixty-second remainder', () => {
    expect(formatFrameTimestamp(59.9996)).toBe('1:00.000')
  })
})
