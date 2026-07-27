import { describe, expect, it } from 'vitest'

import { randomLabelColor } from './labelColor'

function saturationAndLightness(hex: string) {
  const channels = [1, 3, 5].map((start) => Number.parseInt(hex.slice(start, start + 2), 16) / 255)
  const maximum = Math.max(...channels)
  const minimum = Math.min(...channels)
  const lightness = (maximum + minimum) / 2
  const difference = maximum - minimum
  const saturation = difference === 0 ? 0 : difference / (1 - Math.abs(2 * lightness - 1))
  return { saturation: saturation * 100, lightness: lightness * 100 }
}

describe('randomLabelColor', () => {
  it('generates vivid medium-light hex colors', () => {
    for (const random of [0, 0.17, 0.33, 0.5, 0.76, 0.99]) {
      const color = randomLabelColor([], () => random)
      const hsl = saturationAndLightness(color)
      expect(color).toMatch(/^#[0-9a-f]{6}$/)
      expect(hsl.saturation).toBeGreaterThan(75)
      expect(hsl.lightness).toBeGreaterThan(43)
      expect(hsl.lightness).toBeLessThan(53)
    }
  })

  it('retries colors that are too close to an existing hue', () => {
    const existing = randomLabelColor([], () => 0)
    const values = [0, 0.5]
    const candidate = randomLabelColor([existing], () => values.shift() ?? 0.5)

    expect(candidate).not.toBe(existing)
    expect(values).toHaveLength(0)
  })
})
