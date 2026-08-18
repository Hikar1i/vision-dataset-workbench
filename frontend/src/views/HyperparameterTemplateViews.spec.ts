import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const editor = readFileSync(resolve('src/views/HyperparameterTemplateEditorView.vue'), 'utf8')
const list = readFileSync(resolve('src/views/HyperparameterTemplatesView.vue'), 'utf8')
const detail = readFileSync(resolve('src/views/HyperparameterTemplateDetailView.vue'), 'utf8')
const router = readFileSync(resolve('src/router.ts'), 'utf8')

describe('hyperparameter template views', () => {
  it('supports clear, in-place save, and derive from the shared editor', () => {
    expect(editor).toContain("epochs: 100, batch_mode: 'auto'")
    expect(editor).toContain('已清空，核心参数已恢复默认值。')
    expect(editor).toContain('updateHyperparameterTemplate(source.value.id')
    expect(editor).toContain("ElMessageBox.prompt('请输入派生模板名称'")
  })

  it('exposes edit routing only for editable templates and shows update metadata', () => {
    expect(router).toContain('hyperparameter-templates/:id/edit')
    expect(list).toContain("v-if=\"item.can_edit\"")
    expect(list).toContain('item.updated_at')
    expect(detail).toContain("v-if=\"item?.can_edit\"")
    expect(detail).toContain('v{{ item.version }}')
  })
})
