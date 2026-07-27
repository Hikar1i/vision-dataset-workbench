import { json } from './auth'

export type FrameAnnotation = {
  id: string
  label_id: string
  x_min: number
  y_min: number
  x_max: number
  y_max: number
  source: 'manual' | 'model'
  confidence: number | null
}

export type FrameAnnotationSet = {
  frame_id: string
  annotation_revision: number
  items: FrameAnnotation[]
}

const path = (projectId: string, videoId: string, frameId: string) =>
  `/api/v1/projects/${projectId}/videos/${videoId}/frames/${frameId}/annotations`

export const getFrameAnnotations = (
  projectId: string,
  videoId: string,
  frameId: string,
) => json<FrameAnnotationSet>(path(projectId, videoId, frameId))

export const replaceFrameAnnotations = (
  projectId: string,
  videoId: string,
  value: FrameAnnotationSet,
) =>
  json<FrameAnnotationSet>(path(projectId, videoId, value.frame_id), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      annotation_revision: value.annotation_revision,
      items: value.items,
    }),
  })
