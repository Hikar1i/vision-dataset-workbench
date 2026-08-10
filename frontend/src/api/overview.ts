import { json } from './auth'

export type Overview = {
  projects: number
  videos: number
  model_projects: number
  training_tasks: number
  running_tasks: { own: number; global: number }
  task_status: Array<{ status: string; count: number }>
  host: { hostname: string; note: string }
}

export const getOverview = () => json<Overview>('/api/v1/overview')
