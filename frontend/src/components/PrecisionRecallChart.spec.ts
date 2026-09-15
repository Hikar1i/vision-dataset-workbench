import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import PrecisionRecallChart from './PrecisionRecallChart.vue'

const mocks = vi.hoisted(() => ({
  dispose: vi.fn(),
  init: vi.fn(),
  resize: vi.fn(),
  setOption: vi.fn(),
}))

vi.mock('echarts/core', () => ({
  init: mocks.init,
  use: vi.fn(),
}))
vi.mock('echarts/charts', () => ({ LineChart: {} }))
vi.mock('echarts/components', () => ({
  DataZoomComponent: {}, GridComponent: {}, LegendComponent: {}, TooltipComponent: {},
}))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

describe('PrecisionRecallChart', () => {
  it('initializes after an asynchronously loaded curve creates the chart container', async () => {
    mocks.init.mockReturnValue({
      dispose: mocks.dispose,
      resize: mocks.resize,
      setOption: mocks.setOption,
    })
    vi.stubGlobal('matchMedia', () => ({ matches: false }))
    const wrapper = mount(PrecisionRecallChart, {
      props: { curve: { version: 1, kind: 'unavailable', series: [] } },
      global: { stubs: { ElEmpty: true } },
    })

    await wrapper.setProps({
      curve: {
        version: 1,
        kind: 'interactive',
        series: [{ name: 'car', points: [[0.5, 0.8]] }],
      },
    })
    await flushPromises()

    expect(mocks.init).toHaveBeenCalledWith(wrapper.get('.pr-chart').element)
    expect(mocks.setOption).toHaveBeenCalled()
  })
})
