import { describe, expect, it } from 'vitest'

import { applyEnabledPattern, diffEnabledStates, selectFrameRange } from './frameFilter'

const ids = ['f1', 'f2', 'f3', 'f4', 'f5']

describe('frame filter state', () => {
  it('adds an inclusive range without dropping earlier selections', () => {
    expect(selectFrameRange(ids, new Set(['f5']), 'f1', 'f4')).toEqual(
      new Set(['f1', 'f2', 'f3', 'f4', 'f5']),
    )
  })

  it('applies a pattern to every frame in sequence order', () => {
    expect(applyEnabledPattern(ids, {}, [true, false])).toEqual({
      f1: true,
      f2: false,
      f3: true,
      f4: false,
      f5: true,
    })
  })

  it('compresses selected frames before applying a pattern', () => {
    expect(
      applyEnabledPattern(ids, { f1: false, f2: false, f3: false, f4: false, f5: false }, [true, false], new Set(['f2', 'f4', 'f5'])),
    ).toEqual({ f1: false, f2: true, f3: false, f4: false, f5: true })
  })

  it('only returns states that differ from the baseline', () => {
    expect(diffEnabledStates(ids, { f1: true, f2: false }, { f1: true, f2: true })).toEqual([
      { frame_id: 'f2', enabled: true },
    ])
  })
})
