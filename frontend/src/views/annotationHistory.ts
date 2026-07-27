import type { FrameAnnotation } from '../api/annotations'

const clone = (items: FrameAnnotation[]) => items.map((item) => ({ ...item }))

export function createAnnotationHistory(initial: FrameAnnotation[], maxSteps = 100) {
  const limit = Math.max(1, maxSteps)
  let snapshots = [clone(initial)]
  let index = 0

  return {
    push(items: FrameAnnotation[]) {
      snapshots = snapshots.slice(0, index + 1)
      snapshots.push(clone(items))
      if (snapshots.length > limit + 1) snapshots.shift()
      index = snapshots.length - 1
    },
    undo() {
      if (index === 0) return null
      return clone(snapshots[--index]!)
    },
    redo() {
      if (index === snapshots.length - 1) return null
      return clone(snapshots[++index]!)
    },
    reset(items: FrameAnnotation[]) {
      snapshots = [clone(items)]
      index = 0
    },
    canUndo: () => index > 0,
    canRedo: () => index < snapshots.length - 1,
  }
}
