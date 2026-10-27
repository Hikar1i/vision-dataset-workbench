import { describe, expect, it, vi } from 'vitest'

import { getCapabilities, modelRuntimeCapability, type SystemCapabilities } from './capabilities'

const mocks = vi.hoisted(() => ({ json: vi.fn() }))

vi.mock('./auth', () => ({ json: mocks.json }))

describe('capabilities api', () => {
  it('loads the shared runtime capability resource', async () => {
    const response = { features: { tensorrt: { available: false, reason: 'missing' } } }
    mocks.json.mockResolvedValue(response)

    await expect(getCapabilities()).resolves.toBe(response)
    expect(mocks.json).toHaveBeenCalledWith('/api/v1/capabilities')
  })
})

const yes = { available: true, reason: null }
const no = { available: false, reason: 'CPU 环境不支持' }
const gpu = (): SystemCapabilities => ({ gpu: { ...yes, devices: [] }, pytorch_cuda: yes, features: { manual_annotation: yes, yolo_auto_annotation: yes, model_training: yes, onnx_export: yes, onnx_inference: yes, tensorrt: yes } })
it('fails closed before capabilities load and in CPU environments', () => {
  expect(modelRuntimeCapability(undefined, 'pt').available).toBe(false)
  const cpu = gpu(); cpu.gpu = { ...no, devices: [] }
  for (const format of ['pt', 'onnx', 'engine'] as const) expect(modelRuntimeCapability(cpu, format)).toEqual(cpu.gpu)
})
it('checks each format runtime while keeping available formats usable', () => {
  const caps = gpu(); caps.features.tensorrt = no; caps.features.onnx_inference = no
  expect(modelRuntimeCapability(caps, 'pt').available).toBe(true)
  expect(modelRuntimeCapability(caps, 'onnx')).toEqual(no)
  expect(modelRuntimeCapability(caps, 'engine')).toEqual(no)
  caps.features.yolo_auto_annotation = no
  expect(modelRuntimeCapability(caps, 'pt')).toEqual(no)
})
