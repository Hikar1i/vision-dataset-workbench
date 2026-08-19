import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve('src/components/TrainingHyperparameterDialog.vue'), 'utf8')

describe('TrainingHyperparameterDialog layout', () => {
  it('keeps the dialog fixed to the viewport and scrolls only the form pane', () => {
    expect(source).toContain('height: calc(100dvh - 48px);')
    expect(source).toContain('overflow: hidden;')
    expect(source).toContain(':global(.training-hyperparameter-dialog .form-pane)')
    expect(source).toContain('overflow-y: auto;')
    expect(source).toContain('scrollbar-gutter: stable;')
    expect(source).toContain(':global(.training-hyperparameter-dialog .raw-pane)')
  })
})
