export type Point = { x: number; y: number }
export type ImageTransform = { scale: number; x: number; y: number }
export type BoxBounds = {
  x_min: number
  y_min: number
  x_max: number
  y_max: number
}

export function fitImage(
  stageWidth: number,
  stageHeight: number,
  imageWidth: number,
  imageHeight: number,
  padding = 20,
): ImageTransform {
  const availableWidth = Math.max(1, stageWidth - padding * 2)
  const availableHeight = Math.max(1, stageHeight - padding * 2)
  const scale = Math.min(availableWidth / imageWidth, availableHeight / imageHeight)
  return {
    scale,
    x: (stageWidth - imageWidth * scale) / 2,
    y: (stageHeight - imageHeight * scale) / 2,
  }
}

export function stageToImage(
  point: Point,
  fit: ImageTransform,
  zoom: number,
  pan: Point,
): Point {
  const scale = fit.scale * zoom
  return {
    x: (point.x - fit.x - pan.x) / scale,
    y: (point.y - fit.y - pan.y) / scale,
  }
}

export function zoomAtPoint(
  point: Point,
  fit: ImageTransform,
  currentZoom: number,
  targetZoom: number,
  pan: Point,
) {
  const anchor = stageToImage(point, fit, currentZoom, pan)
  const zoom = Math.min(8, Math.max(0.1, targetZoom))
  return {
    zoom,
    pan: {
      x: point.x - fit.x - anchor.x * fit.scale * zoom,
      y: point.y - fit.y - anchor.y * fit.scale * zoom,
    },
  }
}

export function clampBox(
  box: BoxBounds,
  imageWidth: number,
  imageHeight: number,
): BoxBounds | null {
  const clamped = {
    x_min: Math.round(Math.max(0, Math.min(imageWidth, box.x_min))),
    y_min: Math.round(Math.max(0, Math.min(imageHeight, box.y_min))),
    x_max: Math.round(Math.max(0, Math.min(imageWidth, box.x_max))),
    y_max: Math.round(Math.max(0, Math.min(imageHeight, box.y_max))),
  }
  return clamped.x_max - clamped.x_min >= 2 && clamped.y_max - clamped.y_min >= 2
    ? clamped
    : null
}
