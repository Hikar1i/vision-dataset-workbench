/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = (path: string) => readFileSync(resolve(path), 'utf8')

describe('ledger column containment', () => {
  it('keeps header and row cells inside the shared grid tracks', () => {
    const table = source('src/ui/VTable.vue')
    const row = source('src/ui/VRow.vue')

    expect(table).toContain('min-width: 0')
    expect(table).toContain('max-width: 100%')
    expect(table).toContain('text-align: left')
    expect(row).toContain('min-width: 0')
    expect(row).toContain('max-width: 100%')
    expect(row).toContain('overflow: hidden')
    expect(row).toContain('justify-self: stretch')
  })

  it('does not let row content independently size training table tracks', () => {
    const taskList = source('src/views/TrainingTasksView.vue')
    const taskDetail = source('src/views/TrainingTaskDetailView.vue')

    expect(taskList).not.toMatch(/minmax\([^)]*,\s*auto\)/)
    expect(taskDetail).not.toMatch(/minmax\([^)]*,\s*auto\)/)
  })

  it('keeps model-project actions inside their column', () => {
    const projects = source('src/views/ModelProjectsView.vue')

    expect(projects).toContain('106px 106px 148px')
  })

  it('clips workflow details and form controls within their cells', () => {
    const videos = source('src/views/ProjectVideosView.vue')
    const editor = source('src/components/TrainingModelEditor.vue')

    expect(videos).toContain('class="status-detail"')
    expect(videos).toContain('.status-detail')
    expect(editor).toContain('.inline :deep(.el-input-number)')
    expect(editor).toContain('.inline :deep(.el-select)')
  })
})
