import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import VRow from './VRow.vue'

describe('VRow', () => {
  it('exposes recent interaction visually and to assistive technology', () => {
    const recent = mount(VRow, {
      props: { columns: '1fr 1fr', recent: true },
      slots: { default: '<span>A</span><span>B</span>' },
    })
    expect(recent.classes()).toContain('vdw-row--recent')
    expect(recent.attributes('aria-current')).toBe('true')

    const ordinary = mount(VRow, {
      props: { columns: '1fr', recent: false },
      slots: { default: '<span>A</span>' },
    })
    expect(ordinary.classes()).not.toContain('vdw-row--recent')
    expect(ordinary.attributes('aria-current')).toBeUndefined()
  })
})
