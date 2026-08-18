import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CoreHyperparameterFields from './CoreHyperparameterFields.vue'

const stubs = {
  ElFormItem: { template: '<label><slot /></label>' },
  ElInputNumber: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<button data-test="number" @click="$emit(\'update:modelValue\', 200)">{{ modelValue }}</button>',
  },
  ElSlider: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<button data-test="slider" @click="$emit(\'update:modelValue\', 960)">{{ modelValue }}</button>',
  },
  ElSelect: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<button data-test="select" @click="$emit(\'update:modelValue\', \'fraction\')"><slot /></button>',
  },
  ElOption: true,
}

describe('CoreHyperparameterFields', () => {
  it('uses the approved two-row layout and emits core changes', async () => {
    const wrapper = mount(CoreHyperparameterFields, {
      props: { epochs: 100, batchMode: 'auto', batchValue: null, imageSize: 640 },
      global: { stubs },
    })

    expect(wrapper.find('.batch-field').exists()).toBe(true)
    await wrapper.get('[data-test="number"]').trigger('click')
    await wrapper.get('[data-test="slider"]').trigger('click')
    await wrapper.get('[data-test="select"]').trigger('click')

    expect(wrapper.emitted('update:epochs')?.[0]).toEqual([200])
    expect(wrapper.emitted('update:imageSize')?.[0]).toEqual([960])
    expect(wrapper.emitted('update:batchMode')?.[0]).toEqual(['fraction'])
    expect(wrapper.emitted('update:batchValue')?.[0]).toEqual([0.8])
  })

  it('supports the stacked compact layout', () => {
    const wrapper = mount(CoreHyperparameterFields, {
      props: {
        epochs: 100,
        batchMode: 'fixed',
        batchValue: 16,
        imageSize: 640,
        compact: true,
      },
      global: { stubs },
    })
    expect(wrapper.get('.core-fields').classes()).toContain('compact')
  })
})
