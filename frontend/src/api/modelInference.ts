import { ApiError, json } from './auth'

export type ModelInferenceRun = {
  id: string
  model_id: string
  format: 'pt' | 'onnx' | 'engine'
  input_type: 'image' | 'video'
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'
  parameters: { confidence: number; iou: number; image_size: number; max_det: number; stride: number }
  statistics: Record<string, number>
  task_id: string | null
  error: string | null
  saved_at: string | null
  expires_at: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export const getCurrentInference = (modelId: string) =>
  json<ModelInferenceRun | null>(`/api/v1/models/${modelId}/inference/current`)

export const listSavedInference = (modelId: string) =>
  json<ModelInferenceRun[]>(`/api/v1/models/${modelId}/inference/saved`)

export async function createInference(
  modelId: string,
  file: File,
  inputType: 'image' | 'video',
  format: 'pt' | 'onnx' | 'engine',
  parameters: ModelInferenceRun['parameters'],
  replace: boolean,
) {
  const query = new URLSearchParams({
    input_type: inputType,
    format,
    confidence: String(parameters.confidence),
    iou: String(parameters.iou),
    image_size: String(parameters.image_size),
    max_det: String(parameters.max_det),
    stride: String(parameters.stride),
  })
  const response = await fetch(`/api/v1/models/${modelId}/inference?${query}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-Filename': file.name, 'X-Replace-Inference': String(replace) },
    body: file,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(body.detail || '推理请求失败', response.status)
  }
  return response.json() as Promise<ModelInferenceRun>
}

export const getInference = (id: string) => json<ModelInferenceRun>(`/api/v1/model-inference/${id}`)
export const keepInferenceAlive = (id: string) => json<ModelInferenceRun>(`/api/v1/model-inference/${id}/keepalive`, { method: 'POST' })
export const saveInference = (id: string) => json<ModelInferenceRun>(`/api/v1/model-inference/${id}/save`, { method: 'POST' })
export const deleteInference = (id: string) => json<void>(`/api/v1/model-inference/${id}`, { method: 'DELETE' })
export const inferenceFileUrl = (id: string, kind: 'source' | 'preview' | 'result') => `/api/v1/model-inference/${id}/files/${kind}`
