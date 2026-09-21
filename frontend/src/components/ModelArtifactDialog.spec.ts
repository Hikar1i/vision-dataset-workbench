import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ModelArtifactDialog from './ModelArtifactDialog.vue'

const mocks = vi.hoisted(() => ({
  capabilities: vi.fn(),
  list: vi.fn(),
  create: vi.fn(),
  remove: vi.fn(),
}))

vi.mock('../api/capabilities', () => ({ getCapabilities: mocks.capabilities }))
vi.mock('../api/modelArtifacts', () => ({
  listModelArtifacts: mocks.list,
  createModelArtifact: mocks.create,
  deleteModelArtifact: mocks.remove,
  modelArtifactDownloadUrl: (id: string) => `/download/${id}`,
}))

const status = (available: boolean, reason: string | null = null) => ({ available, reason })

function mountDialog() {
  return mount(ModelArtifactDialog, {
    attachTo: document.body,
    props: { modelValue: true, modelId: 'model-id', modelName: 'Helmet detector' },
    global: { plugins: [ElementPlus] },
  })
}

beforeEach(() => {
  document.body.innerHTML = ''
  mocks.list.mockReset().mockResolvedValue([])
  mocks.create.mockReset().mockResolvedValue({
    artifact: { id: 'artifact-id', format: 'onnx', status: 'queued' },
    task: { id: 'task-id' },
  })
  mocks.capabilities.mockReset().mockResolvedValue({
    gpu: { available: true, reason: null, devices: [] },
    pytorch_cuda: status(true),
    features: {
      manual_annotation: status(true),
      yolo_auto_annotation: status(true),
      model_training: status(true),
      onnx_export: status(true),
      onnx_inference: status(true),
      tensorrt: status(true),
    },
  })
})

afterEach(() => { document.body.innerHTML = '' })

describe('ModelArtifactDialog', () => {
  it('creates a dynamic ONNX task with the visible configuration', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    const body = new DOMWrapper(document.body)
    await body.findAll('.el-switch')[0].trigger('click')
    await body.get('[data-test="create-onnx-artifact"]').trigger('click')
    await flushPromises()

    expect(mocks.create).toHaveBeenCalledWith('model-id', {
      format: 'onnx',
      image_size: 640,
      dynamic: true,
      precision: 'fp16',
    })
    expect(wrapper.emitted('changed')).toEqual([[]])
  })

  it('keeps TensorRT disabled and explains the unavailable capability', async () => {
    mocks.capabilities.mockResolvedValue({
      gpu: { available: true, reason: null, devices: [] },
      pytorch_cuda: status(true),
      features: {
        manual_annotation: status(true),
        yolo_auto_annotation: status(true),
        model_training: status(true),
        onnx_export: status(true),
        onnx_inference: status(true),
        tensorrt: status(false, 'TensorRT Builder 初始化失败'),
      },
    })
    mountDialog()
    await flushPromises()
    const button = new DOMWrapper(document.body).get('[data-test="create-engine-artifact"]')

    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('title')).toBe('TensorRT Builder 初始化失败')
  })
})
