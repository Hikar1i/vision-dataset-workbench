/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const base = readFileSync(resolve('src/styles/base.css'), 'utf8')
const tokens = readFileSync(resolve('src/styles/tokens.css'), 'utf8')

describe('global design system', () => {
  it('defines the achromatic chrome and data-colour tokens', () => {
    expect(tokens).toContain('--vdw-app: #edf0f1')
    expect(tokens).toContain('--vdw-rail: #101a1f')
    expect(tokens).toContain('--vdw-solid: #16232a')
    expect(tokens).toContain('--vdw-accent: #00738f')
    expect(tokens).toContain('--vdw-focus-canvas: #0b1216')
  })

  it('keeps every ink level above the WCAG AA threshold', () => {
    // ink-3 承载 13-14px 标签与表格副文本，必须 >= 4.5:1；旧值 #7d8b92 只有 3.51:1
    expect(tokens).toContain('--vdw-ink-3: #637177')
    expect(tokens).not.toContain('#7d8b92')
  })

  it('self-hosts the type system instead of naming uninstalled families', () => {
    // Inter 与 Bahnschrift 在目标机器上未安装，旧声明实际全部回落到 Noto CJK
    expect(base).toContain('@fontsource/ibm-plex-sans')
    expect(base).toContain('@fontsource/jetbrains-mono')
    expect(tokens).toContain('--vdw-sans: "IBM Plex Sans"')
    expect(tokens).toContain('--vdw-mono: "JetBrains Mono"')
    expect(tokens).not.toContain('Bahnschrift')
    expect(tokens).not.toContain('Inter,')
  })

  it('aligns numerals so table columns can be scanned', () => {
    expect(base).toContain('font-variant-numeric: tabular-nums')
  })

  it('keeps interactions restrained and supports reduced motion', () => {
    expect(tokens).toContain('--vdw-motion-fast: 130ms')
    expect(tokens).toContain('--vdw-motion-base: 200ms')
    expect(tokens).toContain('--vdw-ease: cubic-bezier(0.2, 0.7, 0.3, 1)')
    expect(base).not.toContain('translateY(8px)')
    expect(base).not.toContain('scale(0.98)')
    expect(base).not.toContain('@media (max-width: 767px)')
    expect(base).toContain('@media (prefers-reduced-motion: reduce)')
    expect(base).toContain('animation-duration: 0.01ms !important')
  })

  it('transitions real height when expanding so panels do not snap open', () => {
    expect(base).toContain('grid-template-rows: 0fr')
    expect(base).toContain('grid-template-rows: 1fr')
  })
})
