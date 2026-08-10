import { beforeEach, describe, expect, it } from 'vitest'

import {
  forgetResource,
  readRecentResources,
  rememberResource,
  resolveRecentResources,
} from './recentResources'

describe('recent resources', () => {
  beforeEach(() => localStorage.clear())

  it('keeps five unique resources in visit order', () => {
    for (let index = 1; index <= 6; index += 1) {
      rememberResource('models', { id: String(index), name: `model ${index}` })
    }
    expect(readRecentResources('models').map(({ id }) => id)).toEqual(['6', '5', '4', '3', '2'])
    rememberResource('models', { id: '4', name: 'renamed' })
    expect(readRecentResources('models').map(({ id }) => id)).toEqual(['4', '6', '5', '3', '2'])
    expect(forgetResource('models', '5').map(({ id }) => id)).toEqual(['4', '6', '3', '2'])
  })

  it('ignores malformed storage', () => {
    localStorage.setItem('models', '{')
    expect(readRecentResources('models')).toEqual([])
  })

  it('fills recent shortcuts from available server resources', () => {
    expect(resolveRecentResources(
      [{ id: '2', name: 'recent' }, { id: 'gone', name: 'deleted' }],
      Array.from({ length: 6 }, (_, index) => ({ id: String(index + 1), name: `item ${index + 1}` })),
    ).map(({ id }) => id)).toEqual(['2', '1', '3', '4', '5'])
  })
})
