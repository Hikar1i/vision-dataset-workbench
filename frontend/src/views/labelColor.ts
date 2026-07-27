const candidateMemory = new Map<string, string>()
const COLOR_PATTERN = /^#[0-9a-f]{6}$/

function hslToHex(hue: number, saturation: number, lightness: number) {
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation
  const segment = hue / 60
  const intermediate = chroma * (1 - Math.abs((segment % 2) - 1))
  const [red, green, blue] =
    segment < 1 ? [chroma, intermediate, 0]
      : segment < 2 ? [intermediate, chroma, 0]
        : segment < 3 ? [0, chroma, intermediate]
          : segment < 4 ? [0, intermediate, chroma]
            : segment < 5 ? [intermediate, 0, chroma]
              : [chroma, 0, intermediate]
  const match = lightness - chroma / 2
  return `#${[red, green, blue]
    .map((channel) => Math.round((channel + match) * 255).toString(16).padStart(2, '0'))
    .join('')}`
}

function hexHue(color: string) {
  if (!COLOR_PATTERN.test(color.toLowerCase())) return null
  const [red, green, blue] = [1, 3, 5].map(
    (start) => Number.parseInt(color.slice(start, start + 2), 16) / 255,
  )
  const maximum = Math.max(red, green, blue)
  const minimum = Math.min(red, green, blue)
  const difference = maximum - minimum
  if (difference === 0) return null
  const raw = maximum === red
    ? ((green - blue) / difference) % 6
    : maximum === green
      ? (blue - red) / difference + 2
      : (red - green) / difference + 4
  return (raw * 60 + 360) % 360
}

function hueDistance(first: number, second: number) {
  const difference = Math.abs(first - second)
  return Math.min(difference, 360 - difference)
}

export function randomLabelColor(existingColors: string[], random = Math.random) {
  const existingHues = existingColors
    .map(hexHue)
    .filter((hue): hue is number => hue !== null)
  let candidate = hslToHex(0, 0.82, 0.48)
  for (let attempt = 0; attempt < 24; attempt += 1) {
    const hue = Math.floor(random() * 360) % 360
    candidate = hslToHex(hue, 0.82, 0.48)
    if (existingHues.every((existing) => hueDistance(hue, existing) >= 24)) return candidate
  }
  return candidate
}

export function readLabelColorCandidate(projectId: string) {
  const key = `vdw:label-color:${projectId}`
  try {
    return sessionStorage.getItem(key)
  } catch {
    return candidateMemory.get(key) ?? null
  }
}

export function writeLabelColorCandidate(projectId: string, color: string) {
  const key = `vdw:label-color:${projectId}`
  candidateMemory.set(key, color)
  try {
    sessionStorage.setItem(key, color)
  } catch {
    // The in-memory value remains available when browser storage is blocked.
  }
}
