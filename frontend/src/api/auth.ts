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

export type ManagedUser = Omit<CurrentUser, 'status'> & {
  status: 'pending' | 'active' | 'rejected' | 'disabled'
  created_at: string
  reviewed_at: string | null
}

export type UserPage = {
  items: ManagedUser[]
  page: number
  page_size: number
  total: number
}

export type UserAction = 'approve' | 'reject' | 'disable' | 'enable'

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
export const register = (username: string, password: string) =>
  json<{ id: string; username: string; status: 'pending' }>('/api/v1/registrations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
export const changePassword = (current_password: string, new_password: string) =>
  json<CurrentUser>('/api/v1/auth/password', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_password, new_password }),
  })
export const listUsers = (status = '', page = 1) =>
  json<UserPage>(
    `/api/v1/admin/users?${new URLSearchParams({ status, page: String(page) })}`,
  )
export const setUserStatus = (id: string, action: UserAction) =>
  json<ManagedUser>(`/api/v1/admin/users/${id}/${action}`, { method: 'POST' })
