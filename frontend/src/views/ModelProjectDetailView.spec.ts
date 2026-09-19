import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve('src/views/ModelProjectDetailView.vue'), 'utf8')

describe('ModelProjectDetailView', () => {
  it('keeps subpage actions in the body and exposes the compact model action set', () => {
    expect(source).not.toContain("'添加时间'")
    expect(source).toContain('model-list-toolbar')
    expect(source).toContain('evaluation_peak')
    expect(source).toContain('下载 PyTorch 模型')
    expect(source).toContain('在线推理')
    expect(source).toContain('在线评估')
    expect(source).toContain('格式转换')
    expect(source).toContain("source: 'models'")
  })
})
