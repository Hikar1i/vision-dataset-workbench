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

export const listProjects = (page = 1) =>
  json<ProjectPage>(`/api/v1/projects?page=${page}`)

export const createProject = (name: string, description: string) =>
  json<Project>('/api/v1/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  })
