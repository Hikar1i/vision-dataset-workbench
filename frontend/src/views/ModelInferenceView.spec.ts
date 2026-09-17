import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve('src/views/ModelInferenceView.vue'), 'utf8')

describe('ModelInferenceView', () => {
  it('keeps one recoverable session with desktop canvas controls and explicit persistence actions', () => {
    expect(source).toContain('会话 24 小时无访问后清理')
    expect(source).toContain('保存推理结果')
    expect(source).toContain('下载源文件')
    expect(source).toContain('下载检测结果')
    expect(source).toContain('5 * 60 * 1000')
    expect(source).toContain('500 * 1024 * 1024')
    expect(source).toContain('20 * 1024 * 1024')
    expect(source).toContain('<template #meta>')
    expect(source).toContain("请先选择图片或视频")
    expect(source).toContain('aria-controls="inference-advanced-fields"')
  })
})
