import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  readRecentProjects,
  rememberProject,
  resolveProjectShortcuts,
} from './recentProjects'

describe('recent projects', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('moves a revisited project to the front and keeps five entries', () => {
    let now = 0
    vi.spyOn(Date, 'now').mockImplementation(() => ++now)
    for (let index = 1; index <= 6; index += 1) {
      rememberProject({ id: String(index), name: `Project ${index}` })
    }
    rememberProject({ id: '3', name: 'Renamed project' })

    expect(readRecentProjects()).toHaveLength(5)
    expect(readRecentProjects()[0]).toMatchObject({
      id: '3',
      name: 'Renamed project',
    })
  })

  it('ignores invalid stored data', () => {
    localStorage.setItem('vdm.recent-projects', '{broken')
    expect(readRecentProjects()).toEqual([])
  })

  it('pins the active project and fills remaining entries without duplicates', () => {
    const result = resolveProjectShortcuts(
      [{ id: '1', name: 'Recent' }],
      [
        { id: '1', name: 'Duplicate' },
        { id: '2', name: 'Fallback' },
      ],
      { id: '3', name: 'Active' },
    )

    expect(result.map((project) => project.id)).toEqual(['3', '1', '2'])
  })
})
