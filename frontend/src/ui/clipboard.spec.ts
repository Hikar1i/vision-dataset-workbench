import { afterEach, describe, expect, it, vi } from 'vitest'

import { copyText } from './clipboard'

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('copyText', () => {
  it('uses the Clipboard API when available', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })

    await copyText('secret')

    expect(writeText).toHaveBeenCalledWith('secret')
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('falls back to a temporary textarea and restores focus', async () => {
    const button = document.createElement('button')
    document.body.append(button)
    button.focus()
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error('not allowed')) },
    })
    const execCommand = vi.fn().mockReturnValue(true)
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: execCommand,
    })

    await copyText('secret')

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(document.querySelector('textarea')).toBeNull()
    expect(document.activeElement).toBe(button)
  })

  it('rejects when neither copy path succeeds', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: undefined,
    })
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: vi.fn().mockReturnValue(false),
    })

    await expect(copyText('secret')).rejects.toThrow('clipboard copy failed')
    expect(document.querySelector('textarea')).toBeNull()
  })
})
