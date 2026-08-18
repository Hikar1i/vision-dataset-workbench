import type { ProjectTask, Video } from '../api/media'

export type VideoWorkflowStatus = {
  code: string
  primary: string
  detail: string
  flags: string[]
}

const taskName = (task: ProjectTask) => {
  if (task.type === 'extract_frames') return '抽帧'
  if (task.type === 'auto_annotate') return '自动标注'
  if (task.type === 'import_model') return '模型入库'
  return '导入'
}

const timestamp = (value: string | undefined) => Date.parse(value || '') || 0

export function videoWorkflowStatus(video: Video): VideoWorkflowStatus {
  const flags: string[] = []
  if ((video.sampling?.frame_revision ?? 0) > 1) flags.push('已筛帧')
  if (video.has_annotations) flags.push('有标注')
  if (!video.enabled) flags.push('视频停用')

  const result = (code: string, primary: string, detail = '') => ({
    code,
    primary,
    detail,
    flags,
  })
  const task = video.latest_task
  if (task?.status === 'queued') return result(`queued-${task.type}`, `等待${taskName(task)}`)
  if (task?.status === 'running') {
    return result(`running-${task.type}`, `${taskName(task)}中`, `${task.progress}%`)
  }
  if (task?.type === 'auto_annotate' && task.status === 'succeeded') {
    return result('auto-annotated', '自动标注完成')
  }

  const resourceUpdated = Math.max(
    timestamp(video.updated_at),
    timestamp(video.sampling?.updated_at),
  )
  if (
    task
    && (task.status === 'failed' || task.status === 'canceled')
    && timestamp(task.updated_at) > resourceUpdated
  ) {
    if (task.status === 'canceled') return result('task-canceled', `${taskName(task)}已取消`)
    return result('task-failed', `${taskName(task)}失败`, task.error || '查看任务详情')
  }

  if (video.status === 'pending') return result('pending', '等待导入')
  if (video.status === 'unavailable') return result('unavailable', '媒体不可用')

  const sampling = video.sampling
  if (
    sampling
    && sampling.extracted_frames > 0
    && sampling.version !== sampling.applied_version
  ) {
    return result(
      'resampling-required',
      '待重抽帧',
      `当前 ${sampling.extracted_frames} 帧，新方案预计 ${sampling.expected_frames} 帧`,
    )
  }
  if (sampling?.extracted_frames) {
    const detail = sampling.enabled_frames < sampling.extracted_frames
      ? `${sampling.enabled_frames}/${sampling.extracted_frames} 帧启用`
      : `${sampling.extracted_frames} 帧`
    return result('sampled', '已采样', detail)
  }
  if (sampling) return result('configured', '待抽帧', `预计 ${sampling.expected_frames} 帧`)
  return result('ready', '可配置采样')
}

export function videoStatusInfo(video: Video): string {
  const status = videoWorkflowStatus(video)
  return status.detail ? `${status.primary} · ${status.detail}` : status.primary
}
