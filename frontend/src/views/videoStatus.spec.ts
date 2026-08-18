import { describe, expect, it } from 'vitest'

import type { ProjectTask, SamplingSummary, Video } from '../api/media'
import { videoStatusInfo, videoWorkflowStatus } from './videoStatus'

const sampling: SamplingSummary = {
  id: 'plan-id',
  state: 'sampled',
  mode: 'target_frames',
  parameters: { target: 50 },
  output_format: 'jpg',
  output_quality: 2,
  computed_interval: 30,
  expected_frames: 50,
  extracted_frames: 50,
  enabled_frames: 50,
  version: 1,
  applied_version: 1,
  generation: 1,
  frame_revision: 1,
  updated_at: '2026-07-24T01:00:00Z',
}

const task: ProjectTask = {
  id: 'task-id',
  project_id: 'project-id',
  model_project_id: null,
  video_id: 'video-id',
  type: 'extract_frames',
  status: 'succeeded',
  progress: 100,
  error: null,
  result: null,
  cancel_requested: false,
  attempts: 1,
  retry_of_id: null,
  created_at: '2026-07-24T00:00:00Z',
  started_at: '2026-07-24T00:00:01Z',
  finished_at: '2026-07-24T00:00:02Z',
  updated_at: '2026-07-24T00:00:02Z',
}

const video: Video = {
  id: 'video-id',
  short_code: 'TESTV001',
  source_type: 'local',
  title: 'video',
  source_name: 'video.mp4',
  source_url: null,
  duration: 10,
  width: 1920,
  height: 1080,
  fps: 25,
  total_frames: 250,
  file_size: 1024,
  status: 'ready',
  enabled: true,
  version: 1,
  created_at: '2026-07-24T00:00:00Z',
  updated_at: '2026-07-24T00:00:00Z',
  sampling: null,
  latest_task: null,
  has_annotations: false,
}

describe('videoStatusInfo', () => {
  it('prioritizes active and newer failed tasks', () => {
    expect(
      videoStatusInfo({
        ...video,
        latest_task: { ...task, status: 'queued' },
      }),
    ).toBe('等待抽帧')
    expect(
      videoStatusInfo({
        ...video,
        latest_task: { ...task, status: 'running', progress: 42 },
      }),
    ).toBe('抽帧中 · 42%')
    expect(
      videoStatusInfo({
        ...video,
        latest_task: {
          ...task,
          type: 'copy_video',
          status: 'failed',
          error: '磁盘已满',
          updated_at: '2026-07-24T02:00:00Z',
        },
      }),
    ).toBe('导入失败 · 磁盘已满')
    expect(
      videoStatusInfo({
        ...video,
        latest_task: {
          ...task,
          status: 'canceled',
          updated_at: '2026-07-24T02:00:00Z',
        },
      }),
    ).toBe('抽帧已取消')
    expect(
      videoStatusInfo({
        ...video,
        latest_task: { ...task, type: 'auto_annotate', status: 'queued' },
      }),
    ).toBe('等待自动标注')
    expect(
      videoStatusInfo({
        ...video,
        latest_task: { ...task, type: 'auto_annotate', status: 'succeeded' },
      }),
    ).toBe('自动标注完成')
  })

  it('ignores stale failed tasks and reports resource state', () => {
    expect(
      videoStatusInfo({
        ...video,
        sampling,
        latest_task: { ...task, status: 'failed', error: '旧错误' },
      }),
    ).toBe('已采样 · 50 帧')
    expect(videoWorkflowStatus({ ...video, enabled: false }).flags).toEqual(['视频停用'])
    expect(
      videoStatusInfo({
        ...video,
        sampling: { ...sampling, enabled_frames: 38, frame_revision: 2 },
      }),
    ).toBe('已采样 · 38/50 帧启用')
    expect(
      videoStatusInfo({
        ...video,
        sampling: { ...sampling, frame_revision: 2 },
      }),
    ).toBe('已采样 · 50 帧')
  })

  it('reports configured and base media states', () => {
    expect(
      videoStatusInfo({
        ...video,
        sampling: {
          ...sampling,
          state: 'configured',
          expected_frames: 80,
          extracted_frames: 0,
          enabled_frames: 0,
          applied_version: 0,
        },
      }),
    ).toBe('待抽帧 · 预计 80 帧')
    expect(videoStatusInfo({ ...video, status: 'pending' })).toBe('等待导入')
    expect(videoStatusInfo(video)).toBe('可配置采样')
    expect(videoStatusInfo({ ...video, status: 'unavailable' })).toBe('媒体不可用')
  })

  it('reports pending resampling and overlapping work flags', () => {
    const changed = {
      ...video,
      has_annotations: true,
      enabled: false,
      sampling: {
        ...sampling,
        state: 'configured' as const,
        version: 2,
        applied_version: 1,
        expected_frames: 80,
        frame_revision: 2,
      },
    }

    expect(videoStatusInfo(changed)).toBe(
      '待重抽帧 · 当前 50 帧，新方案预计 80 帧',
    )
    expect(videoWorkflowStatus(changed).flags).toEqual(['已筛帧', '有标注', '视频停用'])
  })
})
