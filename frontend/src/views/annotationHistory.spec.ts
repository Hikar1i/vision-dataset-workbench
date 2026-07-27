import { describe, expect, it } from 'vitest'

import type { FrameAnnotation } from '../api/annotations'
import { createAnnotationHistory } from './annotationHistory'

const box: FrameAnnotation = {
  id: 'box-id',
  label_id: 'label-id',
  x_min: 10,
  y_min: 20,
  x_max: 100,
  y_max: 120,
  source: 'manual',
  confidence: null,
}

describe('annotation history', () => {
  it('undoes, redoes, and clears redo after a new edit', () => {
    const history = createAnnotationHistory([])
    history.push([{ ...box, x_min: 20 }])

    expect(history.undo()).toEqual([])
    expect(history.redo()?.[0]?.x_min).toBe(20)
    expect(history.undo()).toEqual([])
    history.push([{ ...box, x_min: 30 }])
    expect(history.redo()).toBeNull()
  })

  it('keeps snapshots isolated from caller mutations', () => {
    const draft = [{ ...box }]
    const history = createAnnotationHistory([])
    history.push(draft)
    draft[0]!.x_min = 50

    expect(history.undo()).toEqual([])
    expect(history.redo()?.[0]?.x_min).toBe(10)
  })

  it('limits the number of undoable edits', () => {
    const history = createAnnotationHistory([], 2)
    history.push([{ ...box, x_min: 11 }])
    history.push([{ ...box, x_min: 12 }])
    history.push([{ ...box, x_min: 13 }])

    expect(history.undo()?.[0]?.x_min).toBe(12)
    expect(history.undo()?.[0]?.x_min).toBe(11)
    expect(history.undo()).toBeNull()
  })

  it('resets when switching frames', () => {
    const history = createAnnotationHistory([])
    history.push([{ ...box }])
    history.reset([{ ...box, x_min: 40 }])

    expect(history.canUndo()).toBe(false)
    expect(history.undo()).toBeNull()
  })
})
