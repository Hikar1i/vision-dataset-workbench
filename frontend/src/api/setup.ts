export type SetupStatus = { initialized: boolean }

export async function getSetupStatus(): Promise<SetupStatus> {
  const response = await fetch('/api/v1/setup/status')
  if (!response.ok) throw new Error('无法读取初始化状态')
  return response.json()
}

export type DirectoryItem = { name: string; path: string }
export type DirectoryPage = {
  path: string
  parent: string | null
  items: DirectoryItem[]
  page: number
  page_size: number
  total: number
}

const setupHeaders = (token: string) => ({
  'X-Setup-Token': token,
  'Content-Type': 'application/json',
})

export async function listSetupDirectories(
  token: string,
  path = '.',
  page = 1,
): Promise<DirectoryPage> {
  const query = new URLSearchParams({ path, page: String(page), page_size: '100' })
  const response = await fetch(`/api/v1/setup/directories?${query}`, {
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
