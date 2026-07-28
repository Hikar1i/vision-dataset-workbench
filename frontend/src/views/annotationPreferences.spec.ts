import { beforeEach, describe, expect, it } from 'vitest'

import {
  loadAnnotationPreference,
  saveAnnotationPreference,
} from './annotationPreferences'

describe('annotation preferences', () => {
  beforeEach(() => localStorage.clear())

  it('stores preferences separately for each project', () => {
    saveAnnotationPreference('project-a', { reuse: true, labelId: 'helmet' })
    expect(loadAnnotationPreference('project-a')).toEqual({ reuse: true, labelId: 'helmet' })
    expect(loadAnnotationPreference('project-b')).toEqual({ reuse: false, labelId: '' })
  })

  it('ignores malformed browser state', () => {
    localStorage.setItem('vdm:annotation-preference:project-a', '{broken')
    expect(loadAnnotationPreference('project-a')).toEqual({ reuse: false, labelId: '' })
  })
})
