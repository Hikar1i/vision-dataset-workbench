import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import XAnyLabelingSettingsDialog from './XAnyLabelingSettingsDialog.vue'

const mocks = vi.hoisted(() => ({ save: vi.fn() }))
vi.mock('../api/models', () => ({ saveXAnyLabelingSetting: mocks.save }))

const setting = {
  configured: true,
  server_url: 'http://127.0.0.1:44444',
  has_api_key: true,
  available: true,
}

function mountDialog() {
  return mount(XAnyLabelingSettingsDialog, {
    props: { modelValue: true, setting },
    global: { plugins: [ElementPlus] },
  })
}

beforeEach(() => {
  document.body.innerHTML = ''
  mocks.save.mockReset()
  mocks.save.mockResolvedValue({ setting, models: [] })
})
afterEach(() => { document.body.innerHTML = '' })

describe('XAnyLabelingSettingsDialog', () => {
  it('retains an existing key when the password is empty', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    const body = new DOMWrapper(document.body)
    await body.get('[data-test="xanylabeling-settings-confirm"]').trigger('click')
    await flushPromises()
    expect(mocks.save).toHaveBeenCalledWith(setting.server_url, 'retain', null)
    expect(wrapper.emitted('saved')).toEqual([[setting, []]])
  })

  it('replaces an existing key when a new key is entered', async () => {
    mountDialog()
    await flushPromises()
    const body = new DOMWrapper(document.body)
    await body.get('[data-test="xanylabeling-api-key"]').setValue('new-key')
    await body.get('[data-test="xanylabeling-settings-confirm"]').trigger('click')
    await flushPromises()
    expect(mocks.save).toHaveBeenCalledWith(setting.server_url, 'replace', 'new-key')
  })

  it('clears an existing key when requested', async () => {
    mountDialog()
    await flushPromises()
    const body = new DOMWrapper(document.body)
    await body.get('[data-test="xanylabeling-clear-api-key"] input').setValue(true)
    await body.get('[data-test="xanylabeling-settings-confirm"]').trigger('click')
    await flushPromises()
    expect(mocks.save).toHaveBeenCalledWith(setting.server_url, 'clear', null)
  })
})
