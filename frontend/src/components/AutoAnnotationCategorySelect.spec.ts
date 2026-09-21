import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it } from 'vitest'

import AutoAnnotationCategorySelect from './AutoAnnotationCategorySelect.vue'

const labels = [
  { id: 'person', name: 'person', enabled: true },
  { id: 'car', name: 'car', enabled: false },
]

describe('AutoAnnotationCategorySelect', () => {
  it('shows enabled labels and a searchable new-category option', async () => {
    const wrapper = mount(AutoAnnotationCategorySelect, {
      props: { modelValue: [], query: '', labels, dataTest: 'categories' },
      global: { plugins: [ElementPlus] },
    })
    const select = wrapper.getComponent({ name: 'ElSelect' })

    expect(wrapper.get('input[role="combobox"]').attributes('aria-label')).toBe('自动标注类别')
    expect(select.findAllComponents({ name: 'ElOption' }).map((item) => item.props('value')))
      .toEqual(['__all__', 'person'])
    select.props('filterMethod')?.('helmet')
    await wrapper.setProps({ query: 'helmet' })

    const options = select.findAllComponents({ name: 'ElOption' })
    expect(options.map((item) => item.props('value'))).toEqual(['helmet'])
    expect(options[0]?.props('label')).toBe('新建类别：helmet')
  })

  it('keeps All mutually exclusive with explicit categories', async () => {
    const wrapper = mount(AutoAnnotationCategorySelect, {
      props: { modelValue: ['person'], query: '', labels },
      global: { plugins: [ElementPlus] },
    })
    const select = wrapper.getComponent({ name: 'ElSelect' })

    select.vm.$emit('change', ['person', '__all__'])
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([['__all__']])

    await wrapper.setProps({ modelValue: ['__all__'] })
    select.vm.$emit('change', ['__all__', 'person'])
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([['person']])
  })
})
