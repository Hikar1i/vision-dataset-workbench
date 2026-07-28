import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FrameAnnotationThumbnail from './FrameAnnotationThumbnail.vue'

describe('FrameAnnotationThumbnail', () => {
  it('keeps annotation coordinates aligned with a contained 4:3 image', () => {
    const wrapper = mount(FrameAnnotationThumbnail, {
      props: {
        imageUrl: '/frame.jpg',
        imageWidth: 1920,
        imageHeight: 1080,
        sequence: 7,
        disabled: true,
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
    expect(wrapper.get('.disabled-badge').text()).toBe('已停用')
    expect(wrapper.get('.sequence').text()).toBe('#7')
  })
})
