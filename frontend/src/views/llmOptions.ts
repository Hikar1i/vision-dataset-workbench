/**
 * 大模型高级参数目录。
 *
 * 后端 `DEFAULT_OPTIONS` 只给出键名和数值，页面若直接渲染就是一排光秃秃的
 * 英文键 + 数字框，用户无法判断该填什么。这里补上中文名、用途说明、合法范围
 * 和单位，让默认设置页能自解释。
 *
 * 键名必须与 backend/services/llm_configs.py 的 DEFAULT_OPTIONS 保持一致。
 */
export type LLMOption = {
  /** 中文名 */
  label: string
  /** 一句话说明这个参数影响什么 */
  note: string
  unit?: string
  min: number
  max: number
  step: number
  /** 小数位数；0 表示整数 */
  precision: number
  /** 分组，用于表单分区 */
  group: 'connection' | 'inference' | 'retry'
}

export const LLM_OPTIONS: Record<string, LLMOption> = {
  connection_timeout_seconds: {
    label: '连接超时',
    note: '与模型服务建立连接的等待上限，超过即判定服务不可用。',
    unit: '秒',
    min: 1,
    max: 300,
    step: 1,
    precision: 0,
    group: 'connection',
  },
  inference_timeout_seconds: {
    label: '推理超时',
    note: '单张图片等待模型返回结果的上限。大图或大模型需要放宽。',
    unit: '秒',
    min: 1,
    max: 3600,
    step: 5,
    precision: 0,
    group: 'connection',
  },
  confidence: {
    label: '置信度阈值',
    note: '低于该置信度的检测框会被丢弃。调高更干净，调低召回更多。',
    min: 0,
    max: 1,
    step: 0.05,
    precision: 2,
    group: 'inference',
  },
  temperature: {
    label: '采样温度',
    note: '越低输出越确定、越可复现；标注任务通常保持较低值。',
    min: 0,
    max: 2,
    step: 0.1,
    precision: 2,
    group: 'inference',
  },
  request_interval_seconds: {
    label: '请求间隔',
    note: '两次请求之间的强制等待。为 0 表示不限速；受限于配额时可调高。',
    unit: '秒',
    min: 0,
    max: 60,
    step: 0.5,
    precision: 1,
    group: 'retry',
  },
  retry_interval_seconds: {
    label: '重试间隔',
    note: '请求失败后等待多久再重试。',
    unit: '秒',
    min: 0,
    max: 300,
    step: 1,
    precision: 1,
    group: 'retry',
  },
  max_retries: {
    label: '最大重试次数',
    note: '单张图片失败后的额外重试次数。为 0 表示不重试。',
    unit: '次',
    min: 0,
    max: 10,
    step: 1,
    precision: 0,
    group: 'retry',
  },
}

export const LLM_OPTION_GROUPS: Array<{
  key: LLMOption['group']
  title: string
  note: string
}> = [
  {
    key: 'connection',
    title: '连接与超时',
    note: '控制等待模型服务响应的时间上限。',
  },
  {
    key: 'inference',
    title: '推理行为',
    note: '影响模型输出的严格程度与稳定性。',
  },
  {
    key: 'retry',
    title: '限速与重试',
    note: '批量标注时保护配额、应对偶发失败。',
  },
]

/** 未在目录中登记的键（后端新增但前端未同步）仍需可编辑，给一个安全兜底。 */
export function llmOption(key: string): LLMOption {
  return (
    LLM_OPTIONS[key] ?? {
      label: key,
      note: '后端新增参数，前端尚未补充说明。',
      min: 0,
      max: Number.MAX_SAFE_INTEGER,
      step: 1,
      precision: 2,
      group: 'retry',
    }
  )
}

/** 按分组归拢一组键，只保留实际存在的键，顺序跟随目录而不是对象键序。 */
export function groupedLLMOptions(keys: string[]) {
  return LLM_OPTION_GROUPS.map((group) => ({
    ...group,
    keys: Object.keys(LLM_OPTIONS)
      .filter((key) => LLM_OPTIONS[key].group === group.key && keys.includes(key)),
  })).filter((group) => group.keys.length > 0)
}

/** 目录里没有的键单独归为一组，避免后端新增参数在页面上消失。 */
export function ungroupedLLMOptions(keys: string[]) {
  return keys.filter((key) => !(key in LLM_OPTIONS))
}
