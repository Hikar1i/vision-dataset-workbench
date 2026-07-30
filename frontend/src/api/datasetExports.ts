import { json } from './auth'

export type DatasetExportStatus = 'queued' | 'running' | 'ready' | 'failed' | 'canceled'

export type DatasetExportLabel = {
  source_label_id: string
  name: string
  mapping: number
  enabled: boolean
}

export type DatasetExport = {
  id: string
  project_id: string
  task_id: string | null
  name: string
  status: DatasetExportStatus
  train_ratio: number
  actual_train_ratio: number | null
  total_frames: number
  train_frames: number
  val_frames: number
  labels: DatasetExportLabel[]
  error: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export type DatasetExportVideoStats = {
  video_id: string
  video_short_code: string
  title: string
  split: 'train' | 'val' | 'excluded'
  exclusion_reason: string | null
  total_frames: number
  enabled_frames: number
  disabled_frames: number
  positive_frames: number
  negative_frames: number
}

export type DatasetExportManifest = {
  version: number
  export_id: string
  name: string
  expected_train_ratio: number
  actual_train_ratio: number
  actual_val_ratio: number
  total_frames: number
  train_frames: number
  val_frames: number
  labels: DatasetExportLabel[]
  train_video_ids: string[]
  val_video_ids: string[]
  disabled_video_ids: string[]
  video_stats: DatasetExportVideoStats[]
}

export type DatasetExportDetail = DatasetExport & {
  absolute_path: string | null
  manifest: DatasetExportManifest | null
}

export type DatasetExportPage = {
  items: DatasetExport[]
  page: number
  page_size: number
  total: number
}

const path = (projectId: string) => `/api/v1/projects/${projectId}/dataset-exports`

export const createDatasetExport = (
  projectId: string,
  payload: { name: string; train_ratio: number; labels: DatasetExportLabel[] },
) => json<DatasetExport>(path(projectId), {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})

export const listDatasetExports = (projectId: string, page = 1, pageSize = 50) =>
  json<DatasetExportPage>(
    `${path(projectId)}?${new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })}`,
  )

export const getDatasetExport = (projectId: string, exportId: string) =>
  json<DatasetExportDetail>(`${path(projectId)}/${exportId}`)

export const datasetExportDownloadUrl = (projectId: string, exportId: string) =>
  `${path(projectId)}/${exportId}/download`

export const deleteDatasetExport = (projectId: string, exportId: string) =>
  json<void>(`${path(projectId)}/${exportId}`, { method: 'DELETE' })
