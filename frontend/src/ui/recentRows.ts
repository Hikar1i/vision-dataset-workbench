import { reactive } from 'vue'

const recentRowIds = reactive<Record<string, string>>({})

export function isRecentRow(scope: string, resourceId: string) {
  return recentRowIds[scope] === resourceId
}

export function markRecentRow(scope: string, resourceId: string) {
  recentRowIds[scope] = resourceId
}

export function markRecentRowFromAction(
  event: MouseEvent,
  scope: string,
  resourceId: string,
) {
  if (!(event.target instanceof Element)) return
  const control = event.target.closest('button, a')
  if (!control || control.matches(':disabled, [aria-disabled="true"]')) return
  markRecentRow(scope, resourceId)
}

export function clearRecentRows() {
  for (const scope of Object.keys(recentRowIds)) delete recentRowIds[scope]
}
