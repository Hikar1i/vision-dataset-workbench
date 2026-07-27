import type { ProjectTask, Video } from '../api/media'

const taskName = (task: ProjectTask) => {
  if (task.type === 'extract_frames') return '抽帧'
  if (task.type === 'auto_annotate') return '自动标注'
  if (task.type === 'import_model') return '模型入库'
  return '导入'
}

const timestamp = (value: string | undefined) => Date.parse(value || '') || 0

export function videoStatusInfo(video: Video): string {
  const task = video.latest_task
  if (task?.status === 'queued') return `等待${taskName(task)}`
  if (task?.status === 'running') return `${taskName(task)}中 · ${task.progress}%`
  if (task?.type === 'auto_annotate' && task.status === 'succeeded') return '自动标注完成'

  const resourceUpdated = Math.max(
    timestamp(video.updated_at),
    timestamp(video.sampling?.updated_at),
  )
  if (
    task &&
    (task.status === 'failed' || task.status === 'canceled') &&
    timestamp(task.updated_at) > resourceUpdated
  ) {
    if (task.status === 'canceled') return `${taskName(task)}已取消`
    return `${taskName(task)}失败 · ${task.error || '查看任务详情'}`
  }

  if (!video.enabled) return '视频已停用，不参与标注与导出'
  const sampling = video.sampling
  if (sampling?.state === 'sampled' && sampling.frame_revision > 1) {
    return sampling.enabled_frames < sampling.extracted_frames
      ? `已筛选 · ${sampling.enabled_frames}/${sampling.extracted_frames} 帧启用`
      : '已恢复全部采样帧'
  }
  if (sampling?.state === 'sampled') return `已采样 · ${sampling.extracted_frames} 帧`
  if (sampling?.state === 'configured') return `待抽帧 · 预计 ${sampling.expected_frames} 帧`
  if (video.status === 'pending') return '等待导入'
  if (video.status === 'ready') return '可配置采样'
  return '媒体不可用'
}
