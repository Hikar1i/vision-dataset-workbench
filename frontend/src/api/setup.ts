import type { FilesystemPage, FilesystemQuery } from './filesystem'

export type SetupStatus = { initialized: boolean }

export async function getSetupStatus(): Promise<SetupStatus> {
  const response = await fetch('/api/v1/setup/status')
  if (!response.ok) throw new Error('无法读取初始化状态')
  return response.json()
}

const setupHeaders = (token: string) => ({
  'X-Setup-Token': token,
  'Content-Type': 'application/json',
})

export async function listSetupDirectories(
  token: string,
  query: FilesystemQuery,
): Promise<FilesystemPage> {
  const params = new URLSearchParams({
    path: query.path,
    page: String(query.page),
    page_size: String(query.pageSize),
    search: query.search,
  })
  const response = await fetch(`/api/v1/setup/directories?${params}`, {
    headers: setupHeaders(token),
  })
  if (!response.ok) throw new Error('无法读取目录')
  return response.json()
}

export async function createSetupDirectory(token: string, parent: string, name: string) {
  const response = await fetch('/api/v1/setup/directories', {
    method: 'POST',
    headers: setupHeaders(token),
    body: JSON.stringify({ parent, name }),
  })
  if (!response.ok) throw new Error('无法创建目录')
  return response.json() as Promise<{ path: string; display_path: string }>
}

export async function initializeWorkspace(
  token: string,
  payload: { parent: string; username: string; password: string },
) {
  const response = await fetch('/api/v1/setup/initialize', {
    method: 'POST',
    headers: setupHeaders(token),
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || '初始化失败')
  }
  return response.json() as Promise<{ initialized: true }>
}
