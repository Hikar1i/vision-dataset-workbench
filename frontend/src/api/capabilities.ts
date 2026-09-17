import { json } from './auth'

export type CapabilityStatus = {
  available: boolean
  reason: string | null
}

export type SystemCapabilities = {
  gpu: CapabilityStatus & {
    devices: Array<{
      index: number
      uuid: string
      name: string
      compute_capability: string
      memory_total_mb: number
    }>
  }
  pytorch_cuda: CapabilityStatus
  features: {
    manual_annotation: CapabilityStatus
    yolo_auto_annotation: CapabilityStatus
    model_training: CapabilityStatus
    onnx_export: CapabilityStatus
    onnx_inference: CapabilityStatus
    tensorrt: CapabilityStatus
  }
}

export const getCapabilities = () =>
  json<SystemCapabilities>('/api/v1/capabilities')
