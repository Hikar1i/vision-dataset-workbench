export type AuthStatus = {
  mode: 'multi' | 'single'
  registration_enabled: boolean
}

export type CurrentUser = {
  id: string
  username: string
  status: 'active'
  is_system_admin: boolean
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...init })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(body.detail || '请求失败', response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export const getAuthStatus = () => json<AuthStatus>('/api/v1/auth/status')
export const getCurrentUser = () => json<CurrentUser>('/api/v1/auth/me')
export const login = (username: string, password: string) =>
  json<CurrentUser>('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
export const logout = () => json<void>('/api/v1/auth/logout', { method: 'POST' })
