export async function copyText(value: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value)
      return
    }
  } catch {
    // Local HTTP deployments may expose the API but reject access.
  }

  const activeElement = document.activeElement instanceof HTMLElement
    ? document.activeElement
    : null
  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.readOnly = true
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  textarea.style.pointerEvents = 'none'
  document.body.append(textarea)

  let copied = false
  try {
    textarea.select()
    copied = document.execCommand?.('copy') ?? false
  } finally {
    textarea.remove()
    activeElement?.focus()
  }
  if (!copied) throw new Error('clipboard copy failed')
}
