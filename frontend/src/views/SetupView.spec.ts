import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

import SetupView from './SetupView.vue'

const replace = vi.fn()

vi.mock('vue-router', () => ({ useRouter: () => ({ replace }) }))

vi.mock('../components/ServerDirectoryPicker.vue', () => ({
  default: {
    props: ['token', 'modelValue'],
    emits: ['update:modelValue'],
    template:
      '<button data-test="pick" @click="$emit(\'update:modelValue\', \'data\')">pick</button>',
  },
}))

describe('SetupView', () => {
  it('submits token, workspace parent, and admin credentials', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ initialized: true }) })
    vi.stubGlobal('fetch', fetchMock)
    replace.mockReset()
    const wrapper = mount(SetupView, { global: { plugins: [ElementPlus] } })
    await wrapper.get('[data-test="token"]').setValue('setup-token')
    await wrapper.get('[data-test="continue"]').trigger('click')
    await wrapper.get('[data-test="pick"]').trigger('click')
    await wrapper.get('[data-test="username"]').setValue('admin')
    await wrapper.get('[data-test="password"]').setValue('correct horse battery staple')
    await wrapper
      .get('[data-test="password-confirmation"]')
      .setValue('correct horse battery staple')
    await wrapper.get('[data-test="initialize"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/setup/initialize',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(replace).toHaveBeenCalledWith('/ready')
  })
})
