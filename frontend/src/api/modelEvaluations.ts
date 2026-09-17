import { ApiError, json } from './auth'
import type { ProjectTask } from './media'

export type EvaluationDataset = {
  id: string
  model_project_id: string
  name: string
  content_sha256: string | null
  classes: string[]
  image_count: number
  label_count: number
  negative_count: number
  total_bytes: number
  status: 'queued' | 'validating' | 'ready' | 'failed'
  task_id: string | null
  error: string | null
  created_at: string
  completed_at: string | null
}

export type ModelEvaluation = {
  id: string
  model_project_id: string
  model_id: string
  model_name: string
  format: 'pt' | 'onnx' | 'engine'
  evaluation_dataset_id: string
  dataset_name: string
  dataset_sha256: string
  class_mapping: Record<string, number>
  config: Record<string, unknown>
  metrics: Record<string, number>
  per_class_metrics: { class_index: number; class_name: string; map50_95: number | null }[]
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'
  task_id: string | null
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  has_confusion_matrix: boolean
  has_pr_curve: boolean
}

export const listEvaluationDatasets = (projectId: string) =>
  json<EvaluationDataset[]>(`/api/v1/model-projects/${projectId}/evaluation-datasets`)

export const listModelEvaluations = (projectId: string) =>
  json<ModelEvaluation[]>(`/api/v1/model-projects/${projectId}/evaluations`)

export async function uploadEvaluationDataset(projectId: string, name: string, file: File) {
  const response = await fetch(
    `/api/v1/model-projects/${projectId}/evaluation-datasets?${new URLSearchParams({ name })}`,
    { method: 'POST', credentials: 'same-origin', headers: { 'X-Filename': file.name }, body: file },
  )
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(body.detail || '测试集上传失败', response.status)
  }
  return response.json() as Promise<{ dataset: EvaluationDataset; task: ProjectTask }>
}

export const deleteEvaluationDataset = (id: string) =>
  json<void>(`/api/v1/evaluation-datasets/${id}`, { method: 'DELETE' })

export const createModelEvaluation = (
  projectId: string,
  modelId: string,
  datasetId: string,
  format: ModelEvaluation['format'],
) => json<{ evaluation: ModelEvaluation; task: ProjectTask }>(
  `/api/v1/model-projects/${projectId}/evaluations`,
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId, dataset_id: datasetId, format }),
  },
)

export const getModelEvaluation = (id: string) =>
  json<ModelEvaluation>(`/api/v1/model-evaluations/${id}`)
export const cancelModelEvaluation = (id: string) =>
  json<void>(`/api/v1/model-evaluations/${id}/cancel`, { method: 'POST' })
export const evaluationPlotUrl = (id: string, kind: 'confusion' | 'pr-curve') =>
  `/api/v1/model-evaluations/${id}/plots/${kind}`
