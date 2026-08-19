import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { clearRecentRows, isRecentRow } from '../ui/recentRows'
import ProjectDatasetsView from './ProjectDatasetsView.vue'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  remove: vi.fn(),
}))

vi.mock('../api/datasetExports', () => ({
  listDatasetExports: mocks.list,
  getDatasetExport: mocks.get,
  deleteDatasetExport: mocks.remove,
  datasetExportDownloadUrl: (projectId: string, exportId: string) =>
    `/api/v1/projects/${projectId}/dataset-exports/${exportId}/download`,
}))

const item = {
  id: 'export-id',
  project_id: 'project-id',
  task_id: 'task-id',
  name: '训练集 v1',
  status: 'ready',
  train_ratio: 0.8,
  actual_train_ratio: 0.75,
  total_frames: 100,
  train_frames: 75,
  val_frames: 25,
  labels: [
    { source_label_id: 'person', name: 'person', mapping: 0, enabled: true },
    { source_label_id: 'car', name: 'car', mapping: 1, enabled: false },
  ],
  error: null,
  created_at: '2026-07-30T08:00:00Z',
  started_at: '2026-07-30T08:00:01Z',
  completed_at: '2026-07-30T08:00:02Z',
}

beforeEach(() => {
  clearRecentRows()
  mocks.list.mockReset()
  mocks.get.mockReset()
  mocks.remove.mockReset()
  mocks.list.mockResolvedValue({ items: [item], page: 1, page_size: 50, total: 1 })
  mocks.get.mockResolvedValue({
    ...item,
    absolute_path: '/home/user/.vision-dataset-workbench/projects/project-id/exports/dataset',
    manifest: {
      version: 1,
      labels: item.labels,
      train_video_ids: ['video-1'],
      val_video_ids: ['video-2'],
      disabled_video_ids: [],
      video_stats: [
        {
          video_id: 'video-1', video_short_code: 'TESTV001', title: 'video', split: 'train',
          exclusion_reason: null, total_frames: 75, enabled_frames: 75, disabled_frames: 0,
          positive_frames: 60, negative_frames: 15,
        },
      ],
    },
  })
  mocks.remove.mockResolvedValue(undefined)
})

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

function mountView(role: 'owner' | 'editor' | 'viewer') {
  return mount(ProjectDatasetsView, {
    attachTo: document.body,
    props: {
      project: {
        id: 'project-id', name: 'project', description: '', creator_id: 'owner-id',
        creator_username: 'owner', role, version: 1,
        created_at: '2026-07-30T00:00:00Z', updated_at: '2026-07-30T00:00:00Z',
      },
    },
    global: { plugins: [ElementPlus] },
  })
}

it('lets a viewer inspect and download without delete controls', async () => {
  const wrapper = mountView('viewer')
  await flushPromises()

  expect(wrapper.text()).toContain('训练集 v1')
  expect(wrapper.get('[data-test="frame-summary-export-id"]').text()).toContain('总计100')
  expect(wrapper.get('[data-test="frame-summary-export-id"]').text()).toContain('训练75')
  expect(wrapper.get('[data-test="frame-summary-export-id"]').text()).toContain('验证25')
  expect(wrapper.get('[data-test="ratio-summary-export-id"]').text()).toContain('期望0.80 : 0.20')
  expect(wrapper.get('[data-test="ratio-summary-export-id"]').text()).toContain('实际0.75 : 0.25')
  expect(wrapper.find('[data-test="delete-export-id"]').exists()).toBe(false)
  expect(wrapper.get('[data-test="download-export-id"]').attributes('href')).toBe(
    '/api/v1/projects/project-id/dataset-exports/export-id/download',
  )
  await wrapper.get('[data-test="detail-export-id"]').trigger('click')
  await flushPromises()
  expect(isRecentRow('project:project-id:datasets', 'export-id')).toBe(true)
  const recentRow = wrapper.get('.el-table__body .el-table__row')
  expect(recentRow.classes()).toContain('vdw-row--recent')
  expect(recentRow.text()).toContain('最近交互')

  const body = new DOMWrapper(document.body)
  expect(body.get('[data-test="dataset-detail-content"]').classes()).toContain(
    'dataset-detail-content',
  )
  const detailRows = body.findAll('.dataset-detail-content .el-table__row')
  expect(detailRows.length).toBeGreaterThan(0)
  expect(detailRows.every((row) => !row.classes().includes('vdw-row--recent'))).toBe(true)
  expect(body.get('[data-test="detail-frame-summary"]').text()).toContain('总计100')
  expect(body.text()).toContain('TESTV001')
  expect(body.text()).toContain('正样本')
  wrapper.unmount()

  const remounted = mountView('viewer')
  await flushPromises()
  expect(remounted.get('.el-table__body .el-table__row').classes()).toContain('vdw-row--recent')
  remounted.unmount()
})

it('marks download interactions but ignores empty action-area clicks', async () => {
  const wrapper = mountView('viewer')
  await flushPromises()

  await wrapper.get('.row-actions').trigger('click')
  expect(isRecentRow('project:project-id:datasets', 'export-id')).toBe(false)

  const download = wrapper.get('[data-test="download-export-id"]')
  download.element.addEventListener('click', (event) => event.preventDefault())
  await download.trigger('click')
  expect(isRecentRow('project:project-id:datasets', 'export-id')).toBe(true)
  wrapper.unmount()
})

it('lets an editor logically delete a completed export', async () => {
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
  const wrapper = mountView('editor')
  await flushPromises()

  await wrapper.get('[data-test="delete-export-id"]').trigger('click')
  expect(isRecentRow('project:project-id:datasets', 'export-id')).toBe(true)
  await flushPromises()
  expect(mocks.remove).toHaveBeenCalledWith('project-id', 'export-id')
  expect(mocks.list).toHaveBeenCalledTimes(2)
  wrapper.unmount()
})
