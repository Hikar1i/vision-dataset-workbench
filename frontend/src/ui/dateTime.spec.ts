import { describe, expect, it } from 'vitest'

import { formatDateTime, splitDateTime } from './dateTime'

describe('dateTime', () => {
  it('formats a local timestamp with fixed-width fields', () => {
    expect(formatDateTime('2026-08-19T09:54:45')).toBe('2026-08-19 09:54:45')
    expect(splitDateTime('2026-08-19T09:54:45')).toEqual({
      date: '2026-08-19',
      time: '09:54:45',
    })
  })

  it.each([null, undefined, '', 'not-a-date'])('uses an em dash for %s', (value) => {
    expect(formatDateTime(value)).toBe('—')
    expect(splitDateTime(value)).toEqual({ date: '—', time: '' })
  })
})
