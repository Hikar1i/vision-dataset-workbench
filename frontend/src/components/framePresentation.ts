export function formatFrameTimestamp(seconds: number) {
  const milliseconds = Math.max(0, Math.round(seconds * 1000))
  const minutes = Math.floor(milliseconds / 60_000)
  const remainder = ((milliseconds % 60_000) / 1000).toFixed(3).padStart(6, '0')
  return `${minutes}:${remainder}`
}

export function formatFrameFileName(shortCode: string, sequence: number, extension: string) {
  return `${shortCode}_frame_${String(sequence).padStart(6, '0')}.${extension}`
}
