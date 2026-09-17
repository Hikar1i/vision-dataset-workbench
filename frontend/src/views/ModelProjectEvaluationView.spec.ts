import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve('src/views/ModelProjectEvaluationView.vue'), 'utf8')

describe('ModelProjectEvaluationView', () => {
  it('documents the controlled zip contract and immutable snapshot workflow', () => {
    expect(source).toContain('测试集为不可变内容快照')
    expect(source).toContain('ZIP 1 GB、解压 5 GB、5000 张图片')
    expect(source).toContain('负样本也必须有同名空 TXT')
    expect(source).toContain('评估记录')
    expect(source).toContain('测试集管理')
    expect(source).toContain('PR Curve')
  })
})
