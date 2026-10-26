import { json } from './auth'
import type { FrameAnnotation } from './annotations'
import type { AutoAnnotationConfig, AutoAnnotationResult } from './models'
import type { ProjectTask } from './media'

export type ImageDirectory = { id: string; name: string; source_relative_path: string; import_id: string; total_images: number; enabled_images: number; labeled_images: number; min_width: number | null; max_width: number | null; min_height: number | null; max_height: number | null }
export type ImageAsset = {
  id: string; directory_id: string; source_relative_path: string; file_name: string
  content_sha256: string; width: number; height: number; file_size: number
  materialization: 'reflink' | 'hardlink' | 'copy'; enabled: boolean
  annotation_status: 'pending' | 'labeled'; annotation_revision: number; version: number
  annotations: FrameAnnotation[]; created_at: string; updated_at: string
}
export type ImageFilters = { directory_id?: string | string[]; search?: string; annotation_status?: 'pending' | 'labeled'; enabled?: boolean; label_id?: string }
export type ImagePage = { items: ImageAsset[]; total: number; page: number; page_size: number; summary?: { enabled_images: number; labeled_images: number } }
export type ImageAnnotationSet = { image_id: string; annotation_revision: number; annotation_status: 'pending' | 'labeled'; items: FrameAnnotation[] }
export type ImageImportFormat = 'images' | 'yolo_detect'
export type ImageImportPreview = {
  new_images?: number; existing_images?: number; duplicate_images?: number
  format: ImageImportFormat; root_name: string; fingerprint: string; ignored_files: number; total_images: number; annotation_count: number
  directories: Array<{new_images?:number; existing_images?:number; duplicate_images?:number; name: string; source_relative_path: string; total_images: number; labeled_images: number; annotation_count: number}>
  source_classes: Array<{ source_id: number; name: string }>
  warnings: Array<{code: string; path: string; message: string}>; errors: Array<{path: string; message: string}>
}
export type ImportClassMapping = { source_id: number; project_label_id: string | null; new_label_name: string | null }
const path = (projectId: string) => `/api/v1/projects/${projectId}`
const post = <T>(url: string, payload: unknown) => json<T>(url, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) })
export function imageQuery(filters: ImageFilters) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (Array.isArray(value)) value.forEach(item => query.append(key, item))
    else if (value !== undefined && value !== '') query.set(key, String(value))
  }
  return query
}
export const listImageDirectories = (projectId: string) => json<ImageDirectory[]>(`${path(projectId)}/image-directories`)
export const listImages = (projectId: string, filters: ImageFilters = {}, page = 1, pageSize: 50 | 100 | 200 = 50) => {
  const query = imageQuery(filters); query.set('page', String(page)); query.set('page_size', String(pageSize))
  return json<ImagePage>(`${path(projectId)}/images?${query}`)
}
export const getImage = (projectId: string, imageId: string) => json<ImageAsset>(`${path(projectId)}/images/${imageId}`)
export const imageFileUrl = (projectId: string, imageId: string) => `${path(projectId)}/images/${imageId}/file`
export const imageThumbnailUrl = (projectId: string, imageId: string) => `${path(projectId)}/images/${imageId}/thumbnail`
export const getImageAnnotations = (projectId: string, imageId: string) => json<ImageAnnotationSet>(`${path(projectId)}/images/${imageId}/annotations`)
export const replaceImageAnnotations = (projectId: string, imageId: string, annotation_revision: number, items: FrameAnnotation[]) => json<ImageAnnotationSet>(`${path(projectId)}/images/${imageId}/annotations`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({annotation_revision, items})})
export const imageNeighbors = (projectId: string, imageId: string, filters: ImageFilters) => json<{previous_id: string | null; next_id: string | null}>(`${path(projectId)}/images/${imageId}/neighbors?${imageQuery(filters)}`)
export const previewImageImport = (projectId: string, root_path: string, ignore_annotations: boolean) => post<ImageImportPreview>(`${path(projectId)}/image-imports/preview`, {root_path, ignore_annotations})
export const importImages = (projectId: string, payload: {root_path: string; ignore_annotations: boolean; format?: ImageImportFormat; fingerprint: string; class_mapping: ImportClassMapping[]; confirm_warnings: boolean}) => post<{import_id: string; task: ProjectTask}>(`${path(projectId)}/image-imports`, payload)
export const setImagesEnabled = (projectId: string, changes: Array<{image_id: string; version: number; enabled: boolean}>) => post<Array<{id: string; version: number; enabled: boolean}>>(`${path(projectId)}/images/enabled`, {changes})
export type ImageVersionItem = {image_id: string; version: number}
export type ImageEnabledResult = {id: string; version: number; enabled: boolean}
export type DuplicateImage = {id: string; file_name: string; directory_name: string}
export type ImageDuplicatesPreview = {fingerprint: string; group_count: number; duplicate_count: number; groups: Array<{keeper: DuplicateImage; duplicates: DuplicateImage[]}>}
export const deleteImages = (projectId: string, items: ImageVersionItem[]) => post<{deleted: string[]}>(`${path(projectId)}/images/delete`, {items})
export const setImagesEnabledByAnnotations = (projectId: string, items: ImageVersionItem[]) => post<{changes: ImageEnabledResult[]}>(`${path(projectId)}/images/enabled-by-annotations`, {items})
export const previewImageDuplicates = (projectId: string) => json<ImageDuplicatesPreview>(`${path(projectId)}/images/duplicates`)
export const disableDuplicateImages = (projectId: string, fingerprint: string) => post<{disabled_count: number; group_count: number}>(`${path(projectId)}/images/duplicates/disable`, {fingerprint})
export const runImageAutoAnnotation = (projectId: string, imageId: string, config: AutoAnnotationConfig) => post<AutoAnnotationResult>(`${path(projectId)}/images/${imageId}/auto-annotations`, config)
export const createImageAutoAnnotation = (projectId: string, image_ids: string[], config: AutoAnnotationConfig, overwrite: boolean, scope: 'all' | 'unannotated' = 'all') => post<ProjectTask>(`${path(projectId)}/images/auto-annotations`, {...config, image_ids, overwrite, scope})
