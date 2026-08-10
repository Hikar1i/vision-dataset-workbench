import { json } from './auth'

export type ParameterDefinition = {
  key: string
  label: string
  group: string
  value_type: 'integer' | 'number' | 'boolean' | 'string' | 'integer_or_null' | 'boolean_or_string'
  default: unknown
  minimum: number | null
  maximum: number | null
  choices: string[]
  step: number
  precision: number
  controls: boolean
}

export type HyperparameterCatalog = { version: string; items: ParameterDefinition[] }
export type BatchMode = 'auto' | 'fixed' | 'fraction'
export type HyperparameterTemplate = {
  id: string
  name: string
  description: string
  epochs: number
  batch_mode: BatchMode
  batch_value: number | null
  image_size: number
  extra_parameters: Record<string, unknown>
  effective_parameters: Record<string, unknown>
  catalog_version: string
  system_key: string | null
  derived_from_id: string | null
  created_by_id: string | null
  can_manage: boolean
  created_at: string
}
export type ValidationIssue = { code: string; message: string; key: string | null; line: number | null; column: number | null }
export type RawValidation = {
  valid: boolean
  normalized: {
    epochs: number
    batch_mode: BatchMode
    batch_value: number | null
    image_size: number
    extra_parameters: Record<string, unknown>
  } | null
  normalized_raw: string | null
  issues: ValidationIssue[]
}

export const getHyperparameterCatalog = () =>
  json<HyperparameterCatalog>('/api/v1/hyperparameter-catalog')
export const listHyperparameterTemplates = () =>
  json<HyperparameterTemplate[]>('/api/v1/hyperparameter-templates')
export const getHyperparameterTemplate = (id: string) =>
  json<HyperparameterTemplate>(`/api/v1/hyperparameter-templates/${id}`)
export const createHyperparameterTemplate = (payload: {
  name: string
  description: string
  epochs: number
  batch_mode: BatchMode
  batch_value: number | null
  image_size: number
  extra_parameters: Record<string, unknown>
  derived_from_id: string | null
}) => json<HyperparameterTemplate>('/api/v1/hyperparameter-templates', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
})
export const validateHyperparameterRaw = (raw: string) =>
  json<RawValidation>('/api/v1/hyperparameter-templates/validate-raw', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ raw }),
  })
export const deleteHyperparameterTemplate = (id: string) =>
  json<void>(`/api/v1/hyperparameter-templates/${id}`, { method: 'DELETE' })
