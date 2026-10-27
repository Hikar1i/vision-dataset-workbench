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

export function modelRuntimeCapability(capabilities: SystemCapabilities | undefined, format: 'pt' | 'onnx' | 'engine'): CapabilityStatus {
  if (!capabilities) return { available: false, reason: '正在检测本地模型运行能力' }
  const checks = [capabilities.gpu, capabilities.features.yolo_auto_annotation]
  if (format === 'onnx') checks.push(capabilities.features.onnx_inference)
  if (format === 'engine') checks.push(capabilities.features.tensorrt)
  return checks.find(item => !item.available) ?? { available: true, reason: null }
}
