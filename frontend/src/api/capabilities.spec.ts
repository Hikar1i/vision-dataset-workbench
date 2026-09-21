import { describe, expect, it, vi } from 'vitest'

import { getCapabilities } from './capabilities'

const mocks = vi.hoisted(() => ({ json: vi.fn() }))

vi.mock('./auth', () => ({ json: mocks.json }))

describe('capabilities api', () => {
  it('loads the shared runtime capability resource', async () => {
    const response = { features: { tensorrt: { available: false, reason: 'missing' } } }
    mocks.json.mockResolvedValue(response)

    await expect(getCapabilities()).resolves.toBe(response)
    expect(mocks.json).toHaveBeenCalledWith('/api/v1/capabilities')
  })
})
