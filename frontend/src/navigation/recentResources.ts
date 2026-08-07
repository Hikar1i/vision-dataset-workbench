export type RecentResource = { id: string; name: string; visited_at: number }

export function readRecentResources(key: string): RecentResource[] {
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? '[]')
    return Array.isArray(value)
      ? value.filter((item): item is RecentResource =>
          typeof item?.id === 'string'
          && typeof item?.name === 'string'
          && typeof item?.visited_at === 'number')
      : []
  } catch {
    return []
  }
}

export function rememberResource(key: string, resource: { id: string; name: string }) {
  const next = [
    { ...resource, visited_at: Date.now() },
    ...readRecentResources(key).filter((item) => item.id !== resource.id),
  ].slice(0, 5)
  localStorage.setItem(key, JSON.stringify(next))
  return next
}

export function forgetResource(key: string, id: string) {
  const next = readRecentResources(key).filter((item) => item.id !== id)
  localStorage.setItem(key, JSON.stringify(next))
  return next
}

export function resolveRecentResources(
  recent: Pick<RecentResource, 'id' | 'name'>[],
  available: { id: string; name: string }[],
) {
  const availableIds = new Set(available.map(({ id }) => id))
  const result = recent.filter(({ id }) => availableIds.has(id))
  for (const resource of available) {
    if (!result.some(({ id }) => id === resource.id)) result.push(resource)
    if (result.length === 5) break
  }
  return result.slice(0, 5)
}
