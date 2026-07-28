export type EnabledState = Record<string, boolean>
export type EnabledChange = { frame_id: string; enabled: boolean }

export function selectFrameRange(
  orderedIds: string[],
  selected: Set<string>,
  anchorId: string,
  targetId: string,
) {
  const anchor = orderedIds.indexOf(anchorId)
  const target = orderedIds.indexOf(targetId)
  const next = new Set(selected)
  if (anchor < 0 || target < 0) return next
  const [start, end] = anchor < target ? [anchor, target] : [target, anchor]
  for (let index = start; index <= end; index += 1) next.add(orderedIds[index])
  return next
}

export function applyEnabledPattern(
  orderedIds: string[],
  draft: EnabledState,
  pattern: boolean[],
  selected?: Set<string>,
) {
  const next = { ...draft }
  const targets = selected ? orderedIds.filter((id) => selected.has(id)) : orderedIds
  targets.forEach((id, index) => { next[id] = pattern[index % pattern.length] })
  return next
}

export function diffEnabledStates(
  orderedIds: string[],
  baseline: EnabledState,
  draft: EnabledState,
): EnabledChange[] {
  return orderedIds
    .filter((id) => baseline[id] !== draft[id])
    .map((frame_id) => ({ frame_id, enabled: draft[frame_id] }))
}
