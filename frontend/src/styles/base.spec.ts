/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve('src/styles/base.css'), 'utf8')

describe('global motion styles', () => {
  it('keeps Element Plus and page motion visible', () => {
    expect(css).toContain('--el-transition-duration: 300ms')
    expect(css).toContain('--el-transition-duration-fast: 200ms')
    expect(css).toContain('translateY(8px)')
    expect(css).toContain('@media (prefers-reduced-motion: reduce)')
    expect(css).toContain('animation-duration: 0.01ms !important')
  })
})
