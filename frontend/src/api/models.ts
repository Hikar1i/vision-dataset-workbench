import type { FrameAnnotation } from './annotations'
import { json } from './auth'
import type { ProjectLabel } from './labels'
import type { ProjectTask } from './media'

export type InferenceModel = {
  id: string
  model_project_id: string
  name: string
  description: string
  parameters: Record<string, unknown>
  kind: 'yolo'
  status: 'copying' | 'ready' | 'failed'
  source_name: string
  error: string | null
  created_at: string
  updated_at: string
}

export type ModelProject = {
  id: string
  name: string
  series_type: 'archive' | 'training'
  system_key: string | null
  created_at: string
}

export type RemoteModelOption = {
  key: string
  model_id: string
  task_id: string | null
  name: string
  batch_processing_mode: 'default' | 'text_prompt'
}

export type XAnyLabelingSetting = {
  configured: boolean
  server_url: string
  has_api_key: boolean
  available: boolean
}

export type AutoAnnotationConfig = {
  source: 'local' | 'xanylabeling'
  model_id: string
  remote_task_id: string | null
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

export const listModelProjects = () => json<ModelProject[]>('/api/v1/model-projects')

export const listModelProjectModels = (modelProjectId: string) =>
  json<InferenceModel[]>(`/api/v1/model-projects/${modelProjectId}/models`)

export const getXAnyLabelingSetting = () =>
  json<XAnyLabelingSetting>('/api/v1/me/x-anylabeling-server')

export const saveXAnyLabelingSetting = (
  serverUrl: string,
  apiKeyMode: 'retain' | 'replace' | 'clear',
  apiKey: string | null,
) => json<{ setting: XAnyLabelingSetting; models: RemoteModelOption[] }>(
  '/api/v1/me/x-anylabeling-server',
  {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      server_url: serverUrl,
      api_key_mode: apiKeyMode,
      api_key: apiKey,
    }),
  },
)

export const listXAnyLabelingModels = () =>
  json<RemoteModelOption[]>('/api/v1/me/x-anylabeling-server/models')

export const registerInferenceModel = (
  projectId: string,
  name: string,
  sourcePath: string,
) =>
  json<{ model: InferenceModel; task: ProjectTask }>(
    `/api/v1/projects/${projectId}/models`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, source_path: sourcePath }),
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
