export type DateTimeParts = { date: string; time: string }

const pad = (value: number) => String(value).padStart(2, '0')

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}:${pad(parsed.getSeconds())}`
}

export function splitDateTime(value: string | null | undefined): DateTimeParts {
  const formatted = formatDateTime(value)
  if (formatted === '—') return { date: formatted, time: '' }
  const [date, time] = formatted.split(' ')
  return { date, time }
}
