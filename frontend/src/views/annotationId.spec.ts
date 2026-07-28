import { describe, expect, it } from 'vitest'

import { createAnnotationId } from './annotationId'

describe('createAnnotationId', () => {
  it('uses randomUUID when available', () => {
    expect(createAnnotationId({ randomUUID: () => 'native-id' })).toBe('native-id')
  })

  it('creates a bounded local id when randomUUID is unavailable', () => {
    const id = createAnnotationId({})
    expect(id).toMatch(/^local-[a-z0-9]+-[a-z0-9]+$/)
    expect(id.length).toBeLessThanOrEqual(36)
  })
})
