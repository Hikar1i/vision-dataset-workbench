import { describe, expect, it } from 'vitest'

import { apiErrorMessage } from './auth'

describe('apiErrorMessage', () => {
  it('keeps string details readable', () => {
    expect(apiErrorMessage('配置不存在')).toBe('配置不存在')
  })

  it('extracts FastAPI validation messages', () => {
    expect(apiErrorMessage([
      { loc: ['body', 'model_id'], msg: 'Field required' },
      { loc: ['body', 'categories'], msg: 'Input should be a valid list' },
    ])).toBe('Field required；Input should be a valid list')
  })

  it('unwraps nested error objects without object coercion', () => {
    const message = apiErrorMessage({ detail: { reason: '模型不可用' } })

    expect(message).toBe('模型不可用')
    expect(message).not.toContain('[object Object]')
  })

  it('uses a stable fallback for empty details', () => {
    expect(apiErrorMessage(null)).toBe('请求失败')
  })
})
