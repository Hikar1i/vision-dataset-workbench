import { json } from './auth'
import type { ProjectTask } from './media'

export type ModelArtifact = {
  id: string
  model_id: string
  format: 'onnx' | 'engine'
  status: 'queued' | 'converting' | 'ready' | 'failed' | 'stale'
  source_model_sha256: string
  export_config: {
    imgsz: number
    batch: number
    dynamic: boolean
    simplify: boolean
    nms: boolean
    precision: 'fp16' | 'fp32' | null
  }
  file_size: number | null
  sha256: string | null
  gpu_uuid: string | null
  gpu_index: number | null
  task_id: string | null
  error: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
}

export const listModelArtifacts = (modelId: string) =>
  json<ModelArtifact[]>(`/api/v1/models/${modelId}/artifacts`)

export const createModelArtifact = (
  modelId: string,
  payload: {
    format: 'onnx' | 'engine'
    image_size: number
    dynamic: boolean
    precision: 'fp16' | 'fp32'
  },
) => json<{ artifact: ModelArtifact; task: ProjectTask }>(
  `/api/v1/models/${modelId}/artifacts`,
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  },
)

export const deleteModelArtifact = (artifactId: string) =>
  json<void>(`/api/v1/model-artifacts/${artifactId}`, { method: 'DELETE' })

export const modelArtifactDownloadUrl = (artifactId: string) =>
  `/api/v1/model-artifacts/${artifactId}/download`
