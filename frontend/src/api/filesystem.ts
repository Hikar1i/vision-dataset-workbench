import { json } from './auth'

export const VIDEO_EXTENSIONS = [
  '3gp',
  'avi',
  'flv',
  'm4v',
  'mkv',
  'mov',
  'mp4',
  'ogv',
  'webm',
  'wmv',
] as const
export const MODEL_EXTENSIONS = ['pt'] as const

export type FilesystemEntry = {
  name: string
  path: string
  type: string
  size: number | null
}

export type FilesystemPage = {
  path: string
  parent: string | null
  items: FilesystemEntry[]
  page: number
  page_size: number
  total: number
}

export type FilesystemQuery = {
  path: string
  page: number
  pageSize: number
  extensions: readonly string[]
  search: string
}

export type LoadFilesystemEntries = (query: FilesystemQuery) => Promise<FilesystemPage>
export type CreateFilesystemDirectory = (
  parent: string,
  name: string,
) => Promise<{ path: string; display_path: string }>

export const listFilesystem: LoadFilesystemEntries = (query) => {
  const params = new URLSearchParams({
    path: query.path,
    page: String(query.page),
    page_size: String(query.pageSize),
    search: query.search,
  })
  query.extensions.forEach((extension) => params.append('extensions', extension))
  return json<FilesystemPage>(`/api/v1/filesystem?${params}`)
}

export const createFilesystemDirectory: CreateFilesystemDirectory = (parent, name) =>
  json<{ path: string; display_path: string }>('/api/v1/filesystem/directories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent, name }),
  })
