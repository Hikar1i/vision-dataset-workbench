export function createAnnotationId(
  source: { randomUUID?: () => string } = globalThis.crypto ?? {},
) {
  return source.randomUUID?.()
    ?? `local-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 15)}`
}
