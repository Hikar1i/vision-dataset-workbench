import { beforeEach, expect, it, vi } from 'vitest'
import { json } from './auth'
import {
  imageQuery, deleteImages, disableDuplicateImages, importImages, previewImageDuplicates,
  previewImageImport, replaceImageAnnotations, setImagesEnabledByAnnotations,
} from './images'

vi.mock('./auth', () => ({ json: vi.fn() }))
beforeEach(() => vi.resetAllMocks())
const base = '/api/v1/projects/project'
function expectRequest(url: string, method: string, payload: unknown) {
  expect(json).toHaveBeenLastCalledWith(`${base}${url}`, {
    method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  })
}

it('previews auto detection and explicitly ignoring annotations without a format', async () => {
  for (const ignore_annotations of [false, true]) {
    await previewImageImport('project', 'source', ignore_annotations)
    expectRequest('/image-imports/preview', 'POST', { root_path: 'source', ignore_annotations })
  }
})

it('imports using the fingerprint and ignore setting without requiring a legacy format', async () => {
  const payload = { root_path: 'source', ignore_annotations: true, fingerprint: 'current', class_mapping: [], confirm_warnings: false }
  await importImages('project', payload)
  expectRequest('/image-imports', 'POST', payload)
  await importImages('project', { ...payload, format: 'images' })
  expectRequest('/image-imports', 'POST', { ...payload, format: 'images' })
})

it('saves empty image annotations with their revision and no confirm_empty field', async () => {
  await replaceImageAnnotations('project', 'image', 3, [])
  expectRequest('/images/image/annotations', 'PUT', { annotation_revision: 3, items: [] })
})

it('sends image ids and versions for deletion and annotation based enablement', async () => {
  const items = [{ image_id: 'image', version: 2 }]
  await deleteImages('project', items)
  expectRequest('/images/delete', 'POST', { items })
  await setImagesEnabledByAnnotations('project', items)
  expectRequest('/images/enabled-by-annotations', 'POST', { items })
})

it('reads duplicates without a write and submits only the confirmed fingerprint', async () => {
  await previewImageDuplicates('project')
  expect(json).toHaveBeenLastCalledWith(`${base}/images/duplicates`)
  await disableDuplicateImages('project', 'confirmed')
  expectRequest('/images/duplicates/disable', 'POST', { fingerprint: 'confirmed' })
})

it('serializes multiple directories as repeated query keys and keeps single-directory compatibility',()=>{
  expect(imageQuery({directory_id:['train','valid'],enabled:false}).toString()).toBe('directory_id=train&directory_id=valid&enabled=false')
  expect(imageQuery({directory_id:'train'}).getAll('directory_id')).toEqual(['train'])
  expect(imageQuery({directory_id:[]}).has('directory_id')).toBe(false)
})
