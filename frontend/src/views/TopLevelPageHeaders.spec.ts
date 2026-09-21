import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const mappings = [
  ['OverviewView', 'DataAnalysis'],
  ['ProjectsView', 'Files'],
  ['ModelProjectsView', 'Box'],
  ['HyperparameterTemplatesView', 'Operation'],
  ['TrainingTasksView', 'Cpu'],
  ['AdminUsersView', 'User'],
  ['LLMConfigsView', 'Setting'],
] as const

describe('top-level page headers', () => {
  it.each(mappings)('%s reuses sidebar icon %s', (view, icon) => {
    const source = readFileSync(resolve(`src/views/${view}.vue`), 'utf8')
    expect(source).toMatch(
      new RegExp(`import \\{[^}]*\\b${icon}\\b[^}]*\\} from '@element-plus/icons-vue'`, 's'),
    )
    expect(source).toContain(`:icon="${icon}"`)
  })
})
