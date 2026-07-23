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
  type: 'copy_video' | 'download_video'
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
