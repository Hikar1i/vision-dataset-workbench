import { json } from './auth'

export type CapabilityStatus = {
  available: boolean
  reason: string | null
}

export type SystemCapabilities = {
  gpu: CapabilityStatus & {
    devices: Array<{ index: number; name: string; memory_total_mb: number }>
  }
  pytorch_cuda: CapabilityStatus
  onnx_cuda: CapabilityStatus
  features: {
    manual_annotation: CapabilityStatus
    yolo_auto_annotation: CapabilityStatus
    grounding_dino_auto_annotation: CapabilityStatus
    model_training: CapabilityStatus
  }
}

export const getCapabilities = () =>
  json<SystemCapabilities>('/api/v1/capabilities')
