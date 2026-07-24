import { json } from './auth'

export type ProjectRole = 'owner' | 'editor' | 'viewer'

export type Project = {
  id: string
  name: string
  description: string
  creator_id: string
  creator_username: string
  role: ProjectRole
  version: number
  created_at: string
  updated_at: string
}

export type ProjectPage = {
  items: Project[]
  page: number
  page_size: number
  total: number
}

export type ProjectMember = {
  id: string
  username: string
  status: string
  role: ProjectRole
  created_at: string
}

export const listProjects = (page = 1, pageSize = 50) =>
  json<ProjectPage>(
    `/api/v1/projects?${new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    })}`,
  )

export const createProject = (name: string, description: string) =>
  json<Project>('/api/v1/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  })

export const getProject = (id: string) => json<Project>(`/api/v1/projects/${id}`)

export const updateProject = (
  id: string,
  name: string,
  description: string,
  version: number,
) =>
  json<Project>(`/api/v1/projects/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description, version }),
  })

export const listMembers = (id: string) =>
  json<ProjectMember[]>(`/api/v1/projects/${id}/members`)

export const addMember = (id: string, username: string, role: 'editor' | 'viewer') =>
  json<ProjectMember>(`/api/v1/projects/${id}/members`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, role }),
  })

export const changeMemberRole = (
  id: string,
  userId: string,
  role: 'editor' | 'viewer',
) =>
  json<ProjectMember>(`/api/v1/projects/${id}/members/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  })

export const removeMember = (id: string, userId: string) =>
  json<void>(`/api/v1/projects/${id}/members/${userId}`, { method: 'DELETE' })
