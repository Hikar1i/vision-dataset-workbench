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
  project_type: 'video' | 'image'
  total_samples: number
  train_samples: number
  val_samples: number
  project_id: string
  task_id: string | null
  name: string
  status: DatasetExportStatus
  train_ratio: number
  actual_train_ratio: number | null
  total_frames: number
  train_frames: number
  val_frames: number
  total_videos: number | null
  train_videos: number | null
  val_videos: number | null
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
  project_type?: 'video' | 'image'
  directory_stats?: ImageDirectoryStats[]
  excluded?: Record<string, number>
  filtered_annotations?: number
  positive_samples?: SplitSampleCounts
  negative_samples?: SplitSampleCounts
  target_positive_samples?: SplitSampleCounts
  target_negative_samples?: SplitSampleCounts
  positive_deviation?: number
  negative_deviation?: number
  stratification_warnings?: ImageStratificationWarning[]
  export_id: string
  name: string
  expected_train_ratio: number
  actual_train_ratio: number
  actual_val_ratio: number
  total_frames: number
  train_frames: number
  val_frames: number
  total_videos?: number
  train_videos?: number
  val_videos?: number
  labels: DatasetExportLabel[]
  total_samples?: number
  train_samples?: number
  val_samples?: number
  class_counts?: Record<'train' | 'val', Record<string, number>>
  directory_rules?: DirectoryRule[]
  split_seed?: number
  train_video_ids?: string[]
  val_video_ids?: string[]
  disabled_video_ids?: string[]
  video_stats?: DatasetExportVideoStats[]
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
  payload: DatasetExportRequest,
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

export type DirectoryRule = {directory_id: string; included: boolean; mode: 'ratio' | 'train' | 'val'; train_ratio: number | null}
export type ImageStratificationWarning = {directory_id: string; kind: 'positive' | 'negative'; reason: 'insufficient_samples' | 'fixed_roles' | 'exact_content_groups'}
export type SplitSampleCounts = {train: number; val: number}
export type ImageDirectoryStats = {
  directory_id: string; name: string; source_relative_path: string
  total_images: number; effective_images: number; train_images: number; val_images: number
  target_train_images: number; deviation: number; deviation_reason: string | null
  positive_images: number; negative_images: number
  train_positive_images: number; val_positive_images: number
  train_negative_images: number; val_negative_images: number
  target_train_positive_images: number; target_val_positive_images: number
  target_train_negative_images: number; target_val_negative_images: number
  positive_deviation: number; negative_deviation: number
  positive_deviation_reason: ImageStratificationWarning['reason'] | null
  negative_deviation_reason: ImageStratificationWarning['reason'] | null
  excluded: Record<string, number>; rule: DirectoryRule
}
export type DatasetExportRequest = {name: string; train_ratio: number; labels: DatasetExportLabel[]; directory_rules?: DirectoryRule[]; split_seed?: number; preview_fingerprint?: string}
export type ImageExportPreview = {
  fingerprint: string; directory_stats: ImageDirectoryStats[]; excluded: Record<string, number>
  total_samples: number; train_samples: number; val_samples: number; actual_train_ratio: number
  filtered_annotations: number; single_training_hint: string
  positive_samples: SplitSampleCounts; negative_samples: SplitSampleCounts
  target_positive_samples: SplitSampleCounts; target_negative_samples: SplitSampleCounts
  positive_deviation: number; negative_deviation: number
  stratification_warnings: ImageStratificationWarning[]
}
export const previewDatasetExport = (projectId: string, payload: DatasetExportRequest) => json<ImageExportPreview>(`${path(projectId)}/preview`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)})
