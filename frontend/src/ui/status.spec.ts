import { describe, expect, it } from 'vitest'

import type { DatasetExportStatus } from '../api/datasetExports'
import { datasetExportStatus, trainingStatus, userStatus } from './status'

/** 与 api/datasetExports.ts 的 DatasetExportStatus 联合类型一一对应 */
const EXPORT_STATUSES: DatasetExportStatus[] = [
  'queued', 'running', 'ready', 'failed', 'canceled',
]

describe('status 映射', () => {
  it('覆盖后端全部数据集导出状态，且不把英文码直接吐给用户', () => {
    for (const status of EXPORT_STATUSES) {
      const mapped = datasetExportStatus(status)
      expect(mapped.label, `${status} 缺少中文名`).not.toBe(status)
      expect(mapped.tone).toBeTruthy()
    }
  })

  it('把导出成功/失败/进行中区分为不同语气', () => {
    // 三者同色会让台账扫读时分不出哪一个需要处理
    expect(datasetExportStatus('ready').tone).toBe('ok')
    expect(datasetExportStatus('failed').tone).toBe('danger')
    expect(datasetExportStatus('running').tone).toBe('run')
  })

  it('未知状态不崩，回落为中性语气', () => {
    expect(datasetExportStatus('brand_new').tone).toBe('idle')
    expect(trainingStatus('brand_new').tone).toBe('idle')
    expect(userStatus('brand_new').tone).toBe('idle')
  })

  it('区分数据准备中与准备失败', () => {
    expect(trainingStatus('preparing')).toEqual({ tone: 'run', label: '准备训练数据' })
    expect(trainingStatus('preparation_failed')).toEqual({
      tone: 'danger', label: '数据准备失败',
    })
  })
})
