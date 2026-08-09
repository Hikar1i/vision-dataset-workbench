/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve('src/styles/base.css'), 'utf8')

describe('global design system', () => {
  it('defines the approved desktop tokens and readable type scale', () => {
    expect(css).toContain('--vdw-canvas: #eef3f6')
    expect(css).toContain('--vdw-rail: #1c3442')
    expect(css).toContain('--vdw-teal: #0f8975')
    expect(css).toContain('--vdw-focus-canvas: #0f1d25')
    expect(css).toContain('--vdw-title: Bahnschrift, "Noto Sans CJK SC", sans-serif')
    expect(css).toContain('--vdw-body: Inter, "Noto Sans CJK SC", system-ui, sans-serif')
    expect(css).toContain('--vdm-sidebar-width: 256px')
    expect(css).toContain('--vdm-sidebar-collapsed-width: 72px')
    expect(css).toContain('--el-font-size-base: 16px')
    expect(css).toContain('--el-component-size: 40px')
  })

  it('keeps interactions restrained and supports reduced motion', () => {
    expect(css).toContain('--vdm-motion-fast: 160ms')
    expect(css).toContain('--vdm-motion-base: 220ms')
    expect(css).not.toContain('translateY(8px)')
    expect(css).not.toContain('scale(0.98)')
    expect(css).not.toContain('@media (max-width: 767px)')
    expect(css).toContain('@media (prefers-reduced-motion: reduce)')
    expect(css).toContain('animation-duration: 0.01ms !important')
  })
})
