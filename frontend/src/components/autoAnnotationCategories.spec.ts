import { describe, expect, it } from 'vitest'

import { resolveAutoAnnotationCategories } from './autoAnnotationCategories'

const labels = [
  { name: 'helmet', enabled: true },
  { name: 'person', enabled: true },
  { name: 'archived', enabled: false },
]

describe('resolveAutoAnnotationCategories', () => {
  it('expands project-all to enabled project labels', () => {
    expect(resolveAutoAnnotationCategories(['__all__'], '', labels)).toEqual({
      categories: ['helmet', 'person'],
      error: '',
    })
  })

  it('rejects project-all when no project category is enabled', () => {
    expect(resolveAutoAnnotationCategories(
      ['__all__'],
      '',
      [{ name: 'old', enabled: false }],
    )).toEqual({
      categories: [],
      error: '本项目暂无启用类别，请先新增或启用类别。',
    })
  })

  it('normalizes explicit and pending categories without project expansion', () => {
    expect(resolveAutoAnnotationCategories(['Person', 'person'], ' Helmet ', labels)).toEqual({
      categories: ['person', 'helmet'],
      error: '',
    })
  })

  it('rejects an empty explicit selection', () => {
    expect(resolveAutoAnnotationCategories([], '', labels)).toEqual({
      categories: [],
      error: '请选择或输入至少一个类别。',
    })
  })
})
