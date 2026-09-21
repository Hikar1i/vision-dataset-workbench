export type AuthStatus = {
  mode: 'multi' | 'single'
}

export type CurrentUser = {
  id: string
  username: string
  status: 'active'
  is_system_admin: boolean
  must_change_password: boolean
}

export type ManagedUser = Omit<CurrentUser, 'status'> & {
  status: 'active' | 'disabled'
  created_at: string
}

export type ProvisionedUser = ManagedUser & { initial_password: string }

export type UserPage = {
  items: ManagedUser[]
  page: number
  page_size: number
  total: number
}

export type UserAction = 'disable' | 'enable'

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

function errorText(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (Array.isArray(value)) {
    return value.map(errorText).filter(Boolean).join('；')
  }
  if (!value || typeof value !== 'object') return ''

  const record = value as Record<string, unknown>
  for (const key of ['message', 'msg', 'detail', 'reason']) {
    const nested = errorText(record[key])
    if (nested) return nested
  }
  const serialized = JSON.stringify(value)
  return serialized === '{}' ? '' : serialized
}

export function apiErrorMessage(detail: unknown): string {
  return errorText(detail) || '请求失败'
}

export async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...init })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(apiErrorMessage(body.detail ?? body), response.status)
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
export const createUser = (username: string) =>
  json<ProvisionedUser>('/api/v1/admin/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  })
export const changePassword = (current_password: string | null, new_password: string) =>
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
export const resetUserPassword = (id: string) =>
  json<ProvisionedUser>(`/api/v1/admin/users/${id}/reset-password`, { method: 'POST' })
