import { json } from './auth'

export type Video = {
  id: string
  source_type: 'local' | 'remote'
  title: string
  source_name: string | null
  source_url: string | null
  duration: number
  width: number
  height: number
  fps: number
  total_frames: number
  file_size: number
  status: 'pending' | 'ready' | 'unavailable'
  version: number
  created_at: string
  updated_at: string
  sampling: SamplingSummary | null
}

export type SamplingSummary = {
  id: string
  state: 'configured' | 'sampled'
  mode: 'target_frames' | 'frame_interval' | 'time_interval'
  parameters: Record<string, number>
  output_format: 'jpg' | 'png'
  output_quality: number
  computed_interval: number | null
  expected_frames: number
  extracted_frames: number
  enabled_frames: number
  version: number
  applied_version: number
  generation: number
  frame_revision: number
}

export type SamplingConfig = {
  mode: SamplingSummary['mode']
  parameters: Record<string, number>
  output_format: SamplingSummary['output_format']
  output_quality: number
}

export type VideoPage = {
  items: Video[]
  page: number
  page_size: number
  total: number
}

export type ProjectTask = {
  id: string
  video_id: string | null
  type: 'copy_video' | 'download_video' | 'extract_frames'
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'
  progress: number
  error: string | null
  result: Record<string, unknown> | null
  cancel_requested: boolean
  attempts: number
  retry_of_id: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  updated_at: string
}

export type TaskPage = {
  items: ProjectTask[]
  page: number
  page_size: number
  total: number
}

export type FilesystemItem = {
  name: string
  path: string
  type: 'directory' | 'file'
  size: number | null
}

export type FilesystemPage = {
  path: string
  parent: string | null
  items: FilesystemItem[]
  page: number
  page_size: number
  total: number
}

export type LocalPreview = { path: string; name: string; size: number }
export type RemotePreview = {
  title: string
  url: string
  duration: number
  extractor: string
  external_id: string
  playlist: string
  playlist_index: number | null
}

export type AcceptedImport = { video: Video; task: ProjectTask }
export type ImportNotice = { input: string; reason: string }
export type ImportBatch = {
  accepted: AcceptedImport[]
  skipped: ImportNotice[]
  rejected: ImportNotice[]
}

export type SamplingNotice = { input: string; reason: string }
export type PlanBatch = {
  accepted: Array<{ video_id: string; plan: SamplingSummary }>
  rejected: SamplingNotice[]
}
export type ExtractionBatch = {
  accepted: Array<{ video_id: string; task: ProjectTask }>
  rejected: SamplingNotice[]
}
export type Frame = {
  id: string
  sequence: number
  source_frame_index: number
  time_offset: number
  enabled: boolean
  created_at: string
}
export type FramePage = {
  items: Frame[]
  page: number
  page_size: number
  total: number
  sampling: SamplingSummary
}

const projectPath = (projectId: string) => `/api/v1/projects/${projectId}`

export const listVideos = (projectId: string, page = 1) =>
  json<VideoPage>(`${projectPath(projectId)}/videos?page=${page}`)

export const listTasks = (projectId: string, page = 1) =>
  json<TaskPage>(`${projectPath(projectId)}/tasks?page=${page}`)

export const listFilesystem = (path = '.', page = 1) =>
  json<FilesystemPage>(
    `/api/v1/filesystem?${new URLSearchParams({ path, kind: 'video', page: String(page) })}`,
  )

export const createFilesystemDirectory = (parent: string, name: string) =>
  json<{ path: string; display_path: string }>('/api/v1/filesystem/directories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent, name }),
  })

export const previewLocal = (projectId: string, path: string) =>
  json<LocalPreview[]>(`${projectPath(projectId)}/imports/local/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })

export const importLocal = (projectId: string, paths: string[]) =>
  json<ImportBatch>(`${projectPath(projectId)}/imports/local`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paths }),
  })

export const previewRemote = (projectId: string, url: string) =>
  json<RemotePreview[]>(`${projectPath(projectId)}/imports/remote/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })

export const importRemote = (
  projectId: string,
  items: Array<{ title: string; url: string }>,
) =>
  json<ImportBatch>(`${projectPath(projectId)}/imports/remote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })

export const cancelTask = (projectId: string, taskId: string) =>
  json<ProjectTask>(`${projectPath(projectId)}/tasks/${taskId}/cancel`, {
    method: 'POST',
  })

export const retryTask = (projectId: string, taskId: string) =>
  json<ProjectTask>(`${projectPath(projectId)}/tasks/${taskId}/retry`, {
    method: 'POST',
  })

export const videoContentUrl = (projectId: string, videoId: string) =>
  `${projectPath(projectId)}/videos/${videoId}/content`

export const videoDownloadUrl = (projectId: string, videoId: string) =>
  `${projectPath(projectId)}/videos/${videoId}/download`

export const videoThumbnailUrl = (projectId: string, videoId: string) =>
  `${projectPath(projectId)}/videos/${videoId}/thumbnail`

export const configureSampling = (
  projectId: string,
  videoIds: string[],
  config: SamplingConfig,
) =>
  json<PlanBatch>(`${projectPath(projectId)}/sampling-plans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_ids: videoIds, ...config }),
  })

export const createExtractions = (projectId: string, videoIds: string[]) =>
  json<ExtractionBatch>(`${projectPath(projectId)}/extractions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_ids: videoIds }),
  })

export const getSamplingPlan = (projectId: string, videoId: string) =>
  json<SamplingSummary>(`${projectPath(projectId)}/videos/${videoId}/sampling-plan`)

export const listFrames = (
  projectId: string,
  videoId: string,
  page = 1,
  enabled?: boolean,
) => {
  const query = new URLSearchParams({ page: String(page) })
  if (enabled !== undefined) query.set('enabled', String(enabled))
  return json<FramePage>(`${projectPath(projectId)}/videos/${videoId}/frames?${query}`)
}

export const setFramesEnabled = (
  projectId: string,
  videoId: string,
  enabled: boolean,
  frameIds: string[] | null,
  frameRevision: number,
) =>
  json<SamplingSummary>(`${projectPath(projectId)}/videos/${videoId}/frames/enabled`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      enabled,
      frame_ids: frameIds,
      frame_revision: frameRevision,
    }),
  })

export const frameImageUrl = (projectId: string, videoId: string, frameId: string) =>
  `${projectPath(projectId)}/videos/${videoId}/frames/${frameId}/image`
