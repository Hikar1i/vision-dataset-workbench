import { describe, expect, it } from 'vitest'

import {
  clampBox,
  fitImage,
  stageToImage,
  zoomAtPoint,
} from './annotationGeometry'

describe('annotation geometry', () => {
  it('fits the complete image into the stage', () => {
    expect(fitImage(1000, 700, 1920, 1080)).toEqual({
      scale: 0.5,
      x: 20,
      y: 80,
    })
  })

  it('converts stage coordinates back to original pixels', () => {
    expect(
      stageToImage(
        { x: 270, y: 230 },
        { scale: 0.5, x: 20, y: 80 },
        2,
        { x: 10, y: -10 },
      ),
    ).toEqual({ x: 240, y: 160 })
  })

  it('keeps the pointer anchored and clamps zoom to 10–800 percent', () => {
    expect(
      zoomAtPoint(
        { x: 520, y: 350 },
        { scale: 0.5, x: 20, y: 80 },
        1,
        99,
        { x: 0, y: 0 },
      ),
    ).toEqual({ zoom: 8, pan: { x: -3500, y: -1890 } })
  })

  it('clamps boxes to the image and rejects sub-pixel shapes', () => {
    expect(
      clampBox(
        { x_min: -4, y_min: 2, x_max: 3000, y_max: 900 },
        1920,
        1080,
      ),
    ).toEqual({ x_min: 0, y_min: 2, x_max: 1920, y_max: 900 })
    expect(
      clampBox({ x_min: 5, y_min: 5, x_max: 6, y_max: 6 }, 1920, 1080),
    ).toBeNull()
  })
})
