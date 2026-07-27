import type { FrameAnnotation } from './annotations'
import { json } from './auth'
import type { ProjectLabel } from './labels'
import type { ProjectTask } from './media'

export type InferenceModel = {
  id: string
  name: string
  kind: 'yolo' | 'grounding_dino'
  status: 'copying' | 'ready' | 'failed'
  source_name: string
  error: string | null
  created_at: string
  updated_at: string
}

export type AutoAnnotationConfig = {
  model_id: string
  categories: string[]
  confidence: number
  iou: number
}

export type DraftAutoAnnotation = FrameAnnotation & { label_name: string }
export type AutoAnnotationResult = {
  items: DraftAutoAnnotation[]
  created_labels: ProjectLabel[]
}

export const listInferenceModels = () => json<InferenceModel[]>('/api/v1/models')

export const registerInferenceModel = (
  projectId: string,
  name: string,
  kind: InferenceModel['kind'],
  sourcePath: string,
) =>
  json<{ model: InferenceModel; task: ProjectTask }>(
    `/api/v1/projects/${projectId}/models`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, kind, source_path: sourcePath }),
    },
  )

const videoPath = (projectId: string, videoId: string) =>
  `/api/v1/projects/${projectId}/videos/${videoId}`

export const runFrameAutoAnnotation = (
  projectId: string,
  videoId: string,
  frameId: string,
  config: AutoAnnotationConfig,
) =>
  json<AutoAnnotationResult>(`${videoPath(projectId, videoId)}/frames/${frameId}/auto-annotations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })

export const createBatchAutoAnnotation = (
  projectId: string,
  videoId: string,
  config: AutoAnnotationConfig,
  overwrite: boolean,
) =>
  json<ProjectTask>(`${videoPath(projectId, videoId)}/auto-annotations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...config, overwrite }),
  })
