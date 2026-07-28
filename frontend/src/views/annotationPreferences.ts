export type AnnotationPreference = { reuse: boolean; labelId: string }

const fallback = (): AnnotationPreference => ({ reuse: false, labelId: '' })
const key = (projectId: string) => `vdm:annotation-preference:${projectId}`

export function loadAnnotationPreference(projectId: string): AnnotationPreference {
  try {
    const value = JSON.parse(localStorage.getItem(key(projectId)) ?? '')
    return typeof value?.reuse === 'boolean' && typeof value?.labelId === 'string'
      ? value
      : fallback()
  } catch {
    return fallback()
  }
}

export function saveAnnotationPreference(
  projectId: string,
  value: AnnotationPreference,
) {
  try {
    localStorage.setItem(key(projectId), JSON.stringify(value))
  } catch {
    // Browser storage is optional; the current page state still works.
  }
}
