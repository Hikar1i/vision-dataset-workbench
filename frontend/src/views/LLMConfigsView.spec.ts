import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearRecentRows, isRecentRow } from '../ui/recentRows'
import LLMConfigsView from './LLMConfigsView.vue'

const mocks = vi.hoisted(() => ({
  list: vi.fn(), defaults: vi.fn(), create: vi.fn(), update: vi.fn(),
  remove: vi.fn(), test: vi.fn(), saveDefaults: vi.fn(),
}))
vi.mock('../api/llm', () => ({
  listLLMConfigs: mocks.list,
  getLLMDefaults: mocks.defaults,
  createLLMConfig: mocks.create,
  updateLLMConfig: mocks.update,
  deleteLLMConfig: mocks.remove,
  testLLMConfig: mocks.test,
  saveLLMDefaults: mocks.saveDefaults,
}))

const defaults = { connection_timeout_seconds: 10, inference_timeout_seconds: 120 }
const config = {
  id: 'config-id', name: 'Qwen VL', description: '', base_url: 'http://localhost:8444/v1',
  api_type: 'openai', model_name: 'qwen-vl', has_api_key: true,
  masked_api_key: 'sk-test-******abcd', enabled: true, available: false,
  last_test_status: 'failed', last_test_latency_ms: 30, advanced_options: {}, version: 1,
  created_at: '2026-08-07T00:00:00Z', updated_at: '2026-08-07T00:00:00Z',
}

beforeEach(() => {
  clearRecentRows()
  vi.clearAllMocks()
  mocks.list.mockReset().mockResolvedValue([])
  mocks.defaults.mockReset().mockResolvedValue(defaults)
})

afterEach(() => { document.body.innerHTML = '' })

describe('LLMConfigsView', () => {
  it('uses a full-width empty state and a blank secret input', async () => {
    const wrapper = mount(LLMConfigsView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    expect(wrapper.get('[data-test="llm-tabs"]').classes()).toContain('llm-tabs')
    expect(wrapper.get('[data-test="llm-empty"]').classes()).toContain('llm-empty')
    await wrapper.get('[data-test="llm-create"]').trigger('click')
    await flushPromises()
    const secret = wrapper.get('input[data-test="llm-api-key"]')
    expect((secret.element as HTMLInputElement).value).toBe('')
    expect(secret.attributes('placeholder')).toContain('留空')
    const advancedToggle = wrapper.get('[data-test="llm-advanced-toggle"]')
    expect(advancedToggle.attributes('aria-expanded')).toBe('false')
    await advancedToggle.trigger('click')
    expect(advancedToggle.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('#llm-advanced-options').exists()).toBe(true)
  })

  it('shows the masked key when editing without filling the secret input', async () => {
    mocks.list.mockResolvedValue([config])
    const wrapper = mount(LLMConfigsView, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    await wrapper.get('[data-test="llm-edit-config-id"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('sk-test-******abcd')
    expect((wrapper.get('input[data-test="llm-api-key"]').element as HTMLInputElement).value).toBe('')
    expect(isRecentRow('llm-configs', 'config-id')).toBe(true)
    await wrapper.get('[data-test="llm-tab-defaults"]').trigger('click')
    await wrapper.get('[data-test="llm-tab-list"]').trigger('click')
    expect(
      wrapper.get('[data-test="llm-edit-config-id"]').element.closest('[role="row"]')?.classList,
    ).toContain('vdw-row--recent')
  })
})
