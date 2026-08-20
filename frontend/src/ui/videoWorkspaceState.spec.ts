import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  clearVideoWorkspaceState,
  readFrameGridScale,
  readVideoListState,
  saveFrameGridScale,
  saveVideoListState,
} from './videoWorkspaceState'

beforeEach(clearVideoWorkspaceState)

describe('video workspace state', () => {
  it('keeps list state per project and frame scale per video', () => {
    saveVideoListState('project-a', { page: 3, pageSize: 100 })
    saveFrameGridScale('project-a', 'video-a', 1.5)

    expect(readVideoListState('project-a')).toEqual({ page: 3, pageSize: 100 })
    expect(readVideoListState('project-b')).toEqual({ page: 1, pageSize: 50 })
    expect(readFrameGridScale('project-a', 'video-a')).toBe(1.5)
    expect(readFrameGridScale('project-a', 'video-b')).toBe(1)
  })

  it('clears all workspace state', () => {
    saveVideoListState('project-a', { page: 2, pageSize: 200 })
    saveFrameGridScale('project-a', 'video-a', 1.25)

    clearVideoWorkspaceState()

    expect(readVideoListState('project-a')).toEqual({ page: 1, pageSize: 50 })
    expect(readFrameGridScale('project-a', 'video-a')).toBe(1)
  })

  it('starts empty after frontend modules reload', async () => {
    saveVideoListState('project-a', { page: 2, pageSize: 100 })
    vi.resetModules()

    const fresh = await import('./videoWorkspaceState')

    expect(fresh.readVideoListState('project-a')).toEqual({ page: 1, pageSize: 50 })
  })
})
