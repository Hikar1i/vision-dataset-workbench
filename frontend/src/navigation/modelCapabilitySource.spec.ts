import { describe, expect, it } from 'vitest'

import { modelCapabilityBackTarget } from './modelCapabilitySource'

describe('modelCapabilityBackTarget', () => {
  const fallback = { to: '/model-projects', label: '返回模型项目' }

  it('returns to the model list for list-origin capability pages', () => {
    expect(modelCapabilityBackTarget('p1', 'm1', 'models', fallback)).toEqual({
      to: '/model-projects/p1/models',
      label: '返回模型列表',
    })
  })

  it('returns to model detail only for a valid detail origin', () => {
    expect(modelCapabilityBackTarget('p1', 'm1', 'detail', fallback)).toEqual({
      to: '/model-projects/p1/models/m1',
      label: '返回模型详情',
    })
    expect(modelCapabilityBackTarget('p1', undefined, 'detail', fallback)).toEqual(fallback)
    expect(modelCapabilityBackTarget('p1', 'm1', 'outside', fallback)).toEqual(fallback)
  })
})
