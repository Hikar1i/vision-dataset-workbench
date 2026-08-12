/**
 * 全系统状态 → 语气 的唯一映射。
 *
 * 重构前每个页面自己写三元表达式决定 el-tag 的 type，同一个状态在不同页面
 * 呈现为不同颜色（训练任务的 running 是 warning 黄，其它页面是 primary 蓝）。
 * 这里集中定义，页面不再自行判断。
 */
export type Tone = 'ok' | 'run' | 'warn' | 'danger' | 'idle'

/** 训练任务与训练运行状态（后端 TrainingStatus / RunStatus） */
const TRAINING: Record<string, { tone: Tone; label: string }> = {
  draft: { tone: 'idle', label: '草稿' },
  preparing: { tone: 'run', label: '准备训练数据' },
  preparation_failed: { tone: 'danger', label: '数据准备失败' },
  queued: { tone: 'idle', label: '排队中' },
  running: { tone: 'run', label: '进行中' },
  canceling: { tone: 'warn', label: '取消中' },
  canceled: { tone: 'idle', label: '已取消' },
  start_failed: { tone: 'danger', label: '启动异常' },
  failed: { tone: 'danger', label: '异常结束' },
  partial: { tone: 'warn', label: '部分完成' },
  succeeded: { tone: 'ok', label: '全部完成' },
}

/** 账号状态（后端 ManagedUser.status） */
const USER: Record<string, { tone: Tone; label: string }> = {
  pending: { tone: 'warn', label: '待审批' },
  active: { tone: 'ok', label: '正常' },
  rejected: { tone: 'danger', label: '已拒绝' },
  disabled: { tone: 'idle', label: '已禁用' },
}

/** 数据集导出状态（后端 DatasetExportStatus） */
const DATASET_EXPORT: Record<string, { tone: Tone; label: string }> = {
  queued: { tone: 'idle', label: '排队中' },
  running: { tone: 'run', label: '导出中' },
  ready: { tone: 'ok', label: '可用' },
  failed: { tone: 'danger', label: '失败' },
  canceled: { tone: 'idle', label: '已取消' },
}

/** 视频工作流状态码（views/videoStatus.ts 产出的 code 前缀） */
const VIDEO_TONES: Array<[RegExp, Tone]> = [
  [/^running-/, 'run'],
  [/^queued-/, 'idle'],
  [/^task-failed$/, 'danger'],
  [/^unavailable$/, 'danger'],
  [/^task-canceled$/, 'idle'],
  [/^resampling-required$/, 'warn'],
  [/^auto-annotated$/, 'ok'],
  [/^sampled$/, 'ok'],
  [/^configured$/, 'idle'],
  [/^pending$/, 'idle'],
  [/^ready$/, 'idle'],
]

export function trainingStatus(status: string) {
  return TRAINING[status] ?? { tone: 'idle' as Tone, label: status }
}

export function datasetExportStatus(status: string) {
  return DATASET_EXPORT[status] ?? { tone: 'idle' as Tone, label: status }
}

export function userStatus(status: string) {
  return USER[status] ?? { tone: 'idle' as Tone, label: status }
}

export function videoTone(code: string): Tone {
  for (const [pattern, tone] of VIDEO_TONES) if (pattern.test(code)) return tone
  return 'idle'
}

/** 启用 / 停用这类布尔状态 */
export function enabledStatus(enabled: boolean) {
  return enabled
    ? { tone: 'ok' as Tone, label: '启用' }
    : { tone: 'idle' as Tone, label: '停用' }
}

/**
 * 进度条填充色跟随语气，保证"完成"永远是绿、"异常"永远是红。
 *
 * idle 用浅灰而不是 --vdw-ink-3：填充是大面积色块，用文字级的深灰会让
 * "草稿""排队中"这类中性状态看起来比进行中和完成更重。
 */
export const TONE_COLOR: Record<Tone, string> = {
  ok: 'var(--vdw-ok)',
  run: 'var(--vdw-accent)',
  warn: 'var(--vdw-warn)',
  danger: 'var(--vdw-danger)',
  idle: 'var(--vdw-line-2)',
}
