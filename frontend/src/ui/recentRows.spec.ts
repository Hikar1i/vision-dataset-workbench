import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  clearRecentRows,
  isRecentRow,
  markRecentRow,
  markRecentRowFromAction,
} from './recentRows'

beforeEach(clearRecentRows)

describe('recent rows', () => {
  it('keeps one independent resource id per list scope', () => {
    markRecentRow('projects', 'project-a')
    markRecentRow('training-tasks', 'task-a')
    markRecentRow('projects', 'project-b')

    expect(isRecentRow('projects', 'project-a')).toBe(false)
    expect(isRecentRow('projects', 'project-b')).toBe(true)
    expect(isRecentRow('training-tasks', 'task-a')).toBe(true)
  })

  it('clears all scopes', () => {
    markRecentRow('projects', 'project-a')
    markRecentRow('llm-configs', 'config-a')

    clearRecentRows()

    expect(isRecentRow('projects', 'project-a')).toBe(false)
    expect(isRecentRow('llm-configs', 'config-a')).toBe(false)
  })

  it('starts empty after the frontend modules reload', async () => {
    markRecentRow('projects', 'project-a')
    vi.resetModules()

    const fresh = await import('./recentRows')

    expect(fresh.isRecentRow('projects', 'project-a')).toBe(false)
  })

  it('marks only enabled buttons and links, not disabled controls or action gaps', () => {
    const button = document.createElement('button')
    const icon = document.createElement('span')
    button.append(icon)
    markRecentRowFromAction({ target: icon } as unknown as MouseEvent, 'projects', 'project-a')
    expect(isRecentRow('projects', 'project-a')).toBe(true)

    const disabled = document.createElement('button')
    disabled.disabled = true
    markRecentRowFromAction({ target: disabled } as unknown as MouseEvent, 'projects', 'project-b')
    expect(isRecentRow('projects', 'project-b')).toBe(false)

    const disabledLink = document.createElement('a')
    disabledLink.setAttribute('aria-disabled', 'true')
    markRecentRowFromAction({ target: disabledLink } as unknown as MouseEvent, 'projects', 'project-c')
    expect(isRecentRow('projects', 'project-c')).toBe(false)

    const actionGap = document.createElement('div')
    markRecentRowFromAction({ target: actionGap } as unknown as MouseEvent, 'projects', 'project-d')
    expect(isRecentRow('projects', 'project-d')).toBe(false)
  })
})
