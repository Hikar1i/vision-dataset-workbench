export type ModelCapabilityBackTarget = {
  to: string
  label: string
}

export function modelCapabilityBackTarget(
  projectId: string,
  modelId: string | undefined,
  source: unknown,
  fallback: ModelCapabilityBackTarget,
): ModelCapabilityBackTarget {
  if (source === 'models') {
    return { to: `/model-projects/${projectId}/models`, label: '返回模型列表' }
  }
  if (source === 'detail' && modelId) {
    return { to: `/model-projects/${projectId}/models/${modelId}`, label: '返回模型详情' }
  }
  return fallback
}
