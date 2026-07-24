export type ProjectShortcut = { id: string; name: string }

type StoredProjectShortcut = ProjectShortcut & { visitedAt: number }

const STORAGE_KEY = 'vdm.recent-projects'
const LIMIT = 5

export function readRecentProjects(): StoredProjectShortcut[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
    if (!Array.isArray(value)) return []
    return value
      .filter(
        (item): item is StoredProjectShortcut =>
          typeof item === 'object' &&
          item !== null &&
          typeof item.id === 'string' &&
          typeof item.name === 'string' &&
          typeof item.visitedAt === 'number',
      )
      .sort((left, right) => right.visitedAt - left.visitedAt)
      .slice(0, LIMIT)
  } catch {
    return []
  }
}

export function rememberProject(project: ProjectShortcut) {
  const projects = [
    { ...project, visitedAt: Date.now() },
    ...readRecentProjects().filter((item) => item.id !== project.id),
  ].slice(0, LIMIT)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(projects))
  return projects
}

export function resolveProjectShortcuts(
  recent: ProjectShortcut[],
  fallback: ProjectShortcut[],
  active?: ProjectShortcut,
) {
  const seen = new Set<string>()
  return [...(active ? [active] : []), ...recent, ...fallback]
    .filter((project) => {
      if (seen.has(project.id)) return false
      seen.add(project.id)
      return true
    })
    .slice(0, LIMIT)
}
