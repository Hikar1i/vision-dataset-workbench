import { describe, expect, it } from 'vitest'

import {
  LLM_OPTIONS,
  groupedLLMOptions,
  llmOption,
  ungroupedLLMOptions,
} from './llmOptions'

/** 与 backend/services/llm_configs.py 的 DEFAULT_OPTIONS 对齐 */
const BACKEND_KEYS = [
  'connection_timeout_seconds',
  'inference_timeout_seconds',
  'confidence',
  'temperature',
  'request_interval_seconds',
  'retry_interval_seconds',
  'max_retries',
]

describe('llmOptions', () => {
  it('documents every parameter the backend actually returns', () => {
    for (const key of BACKEND_KEYS) {
      expect(LLM_OPTIONS[key], `缺少 ${key} 的说明`).toBeDefined()
      const option = LLM_OPTIONS[key]
      expect(option.label).not.toBe(key)
      expect(option.note.length).toBeGreaterThan(8)
      expect(option.max).toBeGreaterThan(option.min)
    }
  })

  it('keeps unknown backend keys editable instead of dropping them', () => {
    // 后端新增参数时页面不能让它消失，否则用户无法再改回来
    const fallback = llmOption('brand_new_knob')
    expect(fallback.label).toBe('brand_new_knob')
    expect(ungroupedLLMOptions([...BACKEND_KEYS, 'brand_new_knob'])).toEqual(['brand_new_knob'])
  })

  it('groups parameters and drops empty groups', () => {
    const groups = groupedLLMOptions(BACKEND_KEYS)
    expect(groups.map((group) => group.key)).toEqual(['connection', 'inference', 'retry'])
    expect(groups.every((group) => group.keys.length > 0)).toBe(true)

    const single = groupedLLMOptions(['confidence'])
    expect(single).toHaveLength(1)
    expect(single[0].keys).toEqual(['confidence'])
  })

  it('gives confidence and temperature fractional precision', () => {
    // 整数步进会让 0.25 这类阈值无法输入
    expect(LLM_OPTIONS.confidence.precision).toBeGreaterThan(0)
    expect(LLM_OPTIONS.temperature.precision).toBeGreaterThan(0)
    expect(LLM_OPTIONS.max_retries.precision).toBe(0)
  })
})
