import { json } from './auth'

export type ProjectLabel = {
  id: string
  name: string
  description_zh: string
  color: string
  sort_order: number
  enabled: boolean
  version: number
  created_at: string
  updated_at: string
}

export type LabelChanges = Partial<
  Pick<ProjectLabel, 'name' | 'description_zh' | 'color' | 'enabled'>
>

const path = (projectId: string) => `/api/v1/projects/${projectId}/labels`

export const listLabels = (projectId: string) => json<ProjectLabel[]>(path(projectId))

export const createLabel = (
  projectId: string,
  name: string,
  descriptionZh: string,
  color: string,
) =>
  json<ProjectLabel>(path(projectId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description_zh: descriptionZh, color }),
  })

export const updateLabel = (
  projectId: string,
  label: ProjectLabel,
  changes: LabelChanges,
) =>
  json<ProjectLabel>(`${path(projectId)}/${label.id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...changes, version: label.version }),
  })

export const reorderLabels = (projectId: string, labelIds: string[]) =>
  json<ProjectLabel[]>(`${path(projectId)}/order`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label_ids: labelIds }),
  })

export const deleteLabel = (projectId: string, labelId: string) =>
  json<void>(`${path(projectId)}/${labelId}`, { method: 'DELETE' })
