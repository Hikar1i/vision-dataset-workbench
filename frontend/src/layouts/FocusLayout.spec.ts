import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FocusLayout from './FocusLayout.vue'

describe('FocusLayout', () => {
  it('reserves a stable focus header and content track', () => {
    const wrapper = mount(FocusLayout, {
      global: { stubs: { RouterView: { template: '<main data-test="focus-content" />' } } },
    })

    expect(wrapper.get('[data-test="focus-brand"]').text()).toBe('VDM / FOCUS')
    expect(wrapper.find('[data-test="focus-content"]').exists()).toBe(true)
  })
})
