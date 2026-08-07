import { json } from './auth'

export type LLMConfig = {
  id: string
  name: string
  description: string
  base_url: string
  api_type: 'openai' | 'anthropic'
  model_name: string
  has_api_key: boolean
  enabled: boolean
  available: boolean
  last_test_status: 'untested' | 'success' | 'failed'
  last_test_latency_ms: number | null
  advanced_options: Record<string, unknown>
  version: number
  created_at: string
  updated_at: string
}

export const listLLMConfigs = () => json<LLMConfig[]>('/api/v1/me/llm-configs')
export const getLLMDefaults = () => json<Record<string, unknown>>('/api/v1/me/llm-configs/defaults')
export const saveLLMDefaults = (options: Record<string, unknown>) => json<Record<string, unknown>>('/api/v1/me/llm-configs/defaults', {
  method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ options }),
})
export const createLLMConfig = (payload: Record<string, unknown>) => json<LLMConfig>('/api/v1/me/llm-configs', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
})
export const updateLLMConfig = (id: string, payload: Record<string, unknown>) => json<LLMConfig>('/api/v1/me/llm-configs/' + id, {
  method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
})
export const deleteLLMConfig = (id: string) => json<void>('/api/v1/me/llm-configs/' + id, { method: 'DELETE' })
export const testLLMConfig = (id: string) => json<{ status: string; available: boolean; latency_ms: number; detail: unknown }>('/api/v1/me/llm-configs/' + id + '/test', { method: 'POST' })
