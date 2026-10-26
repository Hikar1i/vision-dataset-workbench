import { afterEach, expect, it, vi } from 'vitest'
import { createInference } from './modelInference'
import { uploadEvaluationDataset } from './modelEvaluations'

afterEach(() => vi.unstubAllGlobals())

const parameters = { confidence: 0.25, iou: 0.7, image_size: 640, max_det: 300, stride: 1 }

it.each(['图像 100% + #.png', '视频😀.mp4'])('sends an ASCII-safe inference filename: %s', async (name) => {
  const file = new File(['content'], name)
  const inputType = name.endsWith('.mp4') ? 'video' : 'image'
  const result = { id: 'inference' }
  const fetchMock = vi.fn(async (_url: string, options: RequestInit) => {
    const headers = new Headers(options.headers)
    expect(headers.get('X-Filename-Encoded')).toBe(encodeURIComponent(name))
    expect(headers.has('X-Filename')).toBe(false)
    expect(headers.get('X-Replace-Inference')).toBe('true')
    expect(options.body).toBe(file)
    expect(options.credentials).toBe('same-origin')
    return { ok: true, json: async () => result }
  })
  vi.stubGlobal('fetch', fetchMock)
  expect(await createInference('model', file, inputType, 'pt', parameters, true)).toEqual(result)
  expect(fetchMock).toHaveBeenCalledOnce()
  expect(fetchMock.mock.calls[0]![0]).toContain(`input_type=${inputType}`)
})

it('uploads a Chinese evaluation ZIP filename without putting Unicode into headers', async () => {
  const file = new File(['zip'], '安全帽测试集 100%25.zip')
  const result = { dataset: { id: 'dataset' }, task: { id: 'task' } }
  const fetchMock = vi.fn(async (_url: string, options: RequestInit) => {
    const headers = new Headers(options.headers)
    expect(headers.get('X-Filename-Encoded')).toBe(encodeURIComponent(file.name))
    expect(headers.has('X-Filename')).toBe(false)
    expect(options.body).toBe(file)
    return { ok: true, json: async () => result }
  })
  vi.stubGlobal('fetch', fetchMock)
  expect(await uploadEvaluationDataset('project', '测试集 + %', file)).toEqual(result)
  const url = new URL(fetchMock.mock.calls[0]![0], 'http://localhost')
  expect(url.searchParams.get('name')).toBe('测试集 + %')
})

it.each(['inference', 'evaluation'])('keeps %s API errors readable', async (kind) => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 422, json: async () => ({ detail: '文件名无效' }) })))
  const file = new File(['content'], '中文.zip')
  const request = kind === 'inference'
    ? createInference('model', file, 'image', 'pt', parameters, false)
    : uploadEvaluationDataset('project', '测试', file)
  await expect(request).rejects.toMatchObject({ message: '文件名无效', status: 422 })
})
