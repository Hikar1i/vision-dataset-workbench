import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve('src/components/HyperparameterConfigEditor.vue'), 'utf8')
const page = readFileSync(resolve('src/views/HyperparameterTemplateEditorView.vue'), 'utf8')

describe('HyperparameterConfigEditor', () => {
  it('owns the shared form, RAW validation, and catalog parameter controls', () => {
    expect(source).toContain('<CoreHyperparameterFields')
    expect(source).toContain('validateHyperparameterRaw(raw.value)')
    expect(source).toContain('v-for="key in Object.keys(state.extra_parameters)"')
  })

  it('is reused by the template editor instead of duplicating core fields', () => {
    expect(page).toContain('<HyperparameterConfigEditor')
    expect(page).not.toContain('<el-slider')
    expect(page).not.toContain('RAW / YAML')
  })
})
