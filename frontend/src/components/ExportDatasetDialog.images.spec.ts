import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { getProject } from '../api/projects'
import { listLabels } from '../api/labels'
import { listImageDirectories, previewImageDuplicates, disableDuplicateImages } from '../api/images'
import { createDatasetExport, previewDatasetExport, type ImageExportPreview } from '../api/datasetExports'
import ExportDatasetDialog from './ExportDatasetDialog.vue'

vi.mock('../api/projects', () => ({ getProject: vi.fn() }))
vi.mock('../api/labels', () => ({ listLabels: vi.fn() }))
vi.mock('../api/images', () => ({ listImageDirectories: vi.fn(), previewImageDuplicates: vi.fn(), disableDuplicateImages: vi.fn() }))
vi.mock('../api/media', () => ({ listVideos: vi.fn() }))
vi.mock('../api/datasetExports', () => ({ createDatasetExport: vi.fn(), previewDatasetExport: vi.fn() }))
vi.mock('../ui/notify', () => ({ notify: { success: vi.fn() } }))
const preview = (fingerprint = 'current'): ImageExportPreview => ({ fingerprint, directory_stats: [], excluded: { disabled: 1 }, total_samples: 400, train_samples: 240, val_samples: 160, actual_train_ratio: 0.6, filtered_annotations: 0, single_training_hint: '', positive_samples: { train: 120, val: 80 }, negative_samples: { train: 120, val: 80 }, target_positive_samples: { train: 120, val: 80 }, target_negative_samples: { train: 120, val: 80 }, positive_deviation: 0, negative_deviation: 0, stratification_warnings: [] })
const wrappers: VueWrapper[] = []
beforeEach(() => {
  vi.resetAllMocks(); vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  vi.mocked(getProject).mockResolvedValue({ project_type: 'image' } as Awaited<ReturnType<typeof getProject>>)
  vi.mocked(listLabels).mockResolvedValue([{ id: 'helmet', name: 'helmet', description_zh: '', color: '#16866f', enabled: true, sort_order: 0, version: 1, created_at: '', updated_at: '' }])
  vi.mocked(listImageDirectories).mockResolvedValue(['train', 'val', 'default', 'test'].map(id => ({ id, name: id, source_relative_path: `images/${id}`, import_id: 'batch', total_images: 103, enabled_images: 102, labeled_images: 101, min_width: 640, max_width: 640, min_height: 480, max_height: 480 })))
  vi.mocked(previewDatasetExport).mockResolvedValue(preview())
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
  vi.mocked(previewImageDuplicates).mockResolvedValue({ fingerprint: 'duplicates-current', group_count: 1, duplicate_count: 2, groups: [{ keeper: { id: 'keeper', file_name: 'a.jpg', directory_name: 'train' }, duplicates: [{ id: 'b', file_name: 'b.jpg', directory_name: 'val' }, { id: 'c', file_name: 'c.jpg', directory_name: 'default' }] }] })
  vi.mocked(disableDuplicateImages).mockResolvedValue({ disabled_count: 2, group_count: 1 })
})
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.useRealTimers(); document.body.innerHTML = '' })
async function open() {
  const w = mount(ExportDatasetDialog, { props: { modelValue: true, projectId: 'image-project' }, global: { plugins: [ElementPlus], stubs: { ElDialog: { template: '<section><slot/><slot name="footer"/></section>' } } } })
  wrappers.push(w); await flushPromises(); await vi.advanceTimersByTimeAsync(250); await flushPromises()
  await w.get('[data-test="dataset-name"]').setValue('图片快照')
  return w
}

it('submits fixed, inherited and individual directory rules with the latest backend fingerprint', async () => {
  const w = await open()
  const rules = w.findAll('.directory-rule')
  rules[0]!.findAllComponents({ name: 'ElSelect' })[0]!.vm.$emit('update:modelValue', 'train')
  rules[0]!.findAllComponents({ name: 'ElSelect' })[0]!.vm.$emit('change', 'train')
  rules[1]!.findAllComponents({ name: 'ElSelect' })[0]!.vm.$emit('update:modelValue', 'val')
  rules[1]!.findAllComponents({ name: 'ElSelect' })[0]!.vm.$emit('change', 'val')
  rules[3]!.findAllComponents({ name: 'ElSelect' })[1]!.vm.$emit('change', 'own')
  await w.vm.$nextTick()
  rules[3]!.getComponent({ name: 'ElInputNumber' }).vm.$emit('update:modelValue', 0.6)
  await w.vm.$nextTick()
  expect(w.get('[data-test="submit-export"]').attributes('disabled')).toBeDefined()
  await vi.advanceTimersByTimeAsync(250); await flushPromises()
  const expectedRules = [
    { directory_id: 'train', included: true, mode: 'train', train_ratio: null },
    { directory_id: 'val', included: true, mode: 'val', train_ratio: null },
    { directory_id: 'default', included: true, mode: 'ratio', train_ratio: null },
    { directory_id: 'test', included: true, mode: 'ratio', train_ratio: 0.6 },
  ]
  expect(previewDatasetExport).toHaveBeenLastCalledWith('image-project', expect.objectContaining({ train_ratio: 0.8, directory_rules: expectedRules }))
  expect(w.text()).toContain('训练 240 · 验证 160 · 训练比例 60.0%')
  await w.get('[data-test="submit-export"]').trigger('click'); await flushPromises()
  expect(createDatasetExport).toHaveBeenCalledWith('image-project', { name: '图片快照', train_ratio: 0.8, labels: [{ source_label_id: 'helmet', name: 'helmet', mapping: 0, enabled: true }], directory_rules: expectedRules, split_seed: 0, preview_fingerprint: 'current' })
})

it('shows each directory source and pending/disabled counts before exporting', async () => {
  const w = await open()
  for (const row of w.findAll('.directory-rule')) {
    expect(row.text()).toContain('images/')
    expect(row.text()).toContain('待标注 2')
    expect(row.text()).toContain('停用 1')
  }
})

it('invalidates preview for excluded directories and fixed modes clear their custom ratio', async () => {
  const w = await open(); const row = w.findAll('.directory-rule')[3]!
  const selects = row.findAllComponents({ name: 'ElSelect' })
  selects[1]!.vm.$emit('change', 'own'); await w.vm.$nextTick()
  row.getComponent({ name: 'ElInputNumber' }).vm.$emit('update:modelValue', 0.6)
  selects[0]!.vm.$emit('update:modelValue', 'train'); selects[0]!.vm.$emit('change', 'train')
  row.getComponent({ name: 'ElCheckbox' }).vm.$emit('update:modelValue', false); await w.vm.$nextTick()
  await vi.advanceTimersByTimeAsync(250); await flushPromises()
  const rules = vi.mocked(previewDatasetExport).mock.calls.at(-1)?.[1].directory_rules
  expect(rules?.[3]).toEqual({ directory_id: 'test', included: false, mode: 'train', train_ratio: null })
})

it('keeps a visible waiting region and discards an older preview response', async () => {
  const w = await open()
  let finish!: (value: ImageExportPreview) => void
  vi.mocked(previewDatasetExport).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  w.getComponent({ name: 'ElSlider' }).vm.$emit('update:modelValue', 0.7); await w.vm.$nextTick()
  await vi.advanceTimersByTimeAsync(250); await flushPromises()
  expect(w.get('[data-test="image-export-preview"]').text()).toContain('正在计算目录划分')
  expect(w.get('[data-test="submit-export"]').attributes('disabled')).toBeDefined()
  w.getComponent({ name: 'ElSlider' }).vm.$emit('update:modelValue', 0.6); await w.vm.$nextTick()
  vi.mocked(previewDatasetExport).mockResolvedValueOnce(preview('newest'))
  await vi.advanceTimersByTimeAsync(250); await flushPromises()
  finish({ ...preview('obsolete'), train_samples: 1 }); await flushPromises()
  await w.get('[data-test="submit-export"]').trigger('click'); await flushPromises()
  expect(vi.mocked(createDatasetExport).mock.calls[0]?.[1].preview_fingerprint).toBe('newest')
})

it('blocks empty exports, shows errors and retries the preview explicitly', async () => {
  const w = await open()
  vi.mocked(previewDatasetExport).mockRejectedValueOnce(new Error('重复图固定划分冲突'))
  w.getComponent({ name: 'ElSlider' }).vm.$emit('update:modelValue', 0.7); await w.vm.$nextTick()
  await vi.advanceTimersByTimeAsync(250); await flushPromises()
  expect(w.text()).toContain('重复图固定划分冲突')
  expect(w.get('[data-test="submit-export"]').attributes('disabled')).toBeDefined()
  vi.mocked(previewDatasetExport).mockResolvedValueOnce({ ...preview(), total_samples: 0 })
  await w.get('[data-test="retry-image-export-preview"]').trigger('click'); await flushPromises()
  expect(w.text()).toContain('没有可导出的有效图片')
  expect(w.get('[data-test="submit-export"]').attributes('disabled')).toBeDefined()
})

async function duplicateFailure() {
  vi.mocked(previewDatasetExport).mockRejectedValueOnce(new Error('完全相同图片被同时指定训练集和验证集'))
  return open()
}

it('only recalculates the preview when requested and explains that it has no side effects', async () => {
  const w = await duplicateFailure()
  const action = w.get('[data-test="retry-image-export-preview"]')
  expect(action.text()).toBe('重新计算划分')
  expect(action.attributes('title')).toContain('不修改图像、标注或启用状态')
  const count = vi.mocked(previewDatasetExport).mock.calls.length
  await action.trigger('click'); await flushPromises()
  expect(previewDatasetExport).toHaveBeenCalledTimes(count + 1)
  expect(previewImageDuplicates).not.toHaveBeenCalled()
  expect(disableDuplicateImages).not.toHaveBeenCalled()
  expect(createDatasetExport).not.toHaveBeenCalled()
})

it('confirms project-wide duplicate disablement, refreshes sources and preserves export configuration', async () => {
  vi.mocked(listLabels).mockResolvedValue(['helmet', 'car'].map(id => ({id, name: id, description_zh: '', color: '#16866f', enabled: true, sort_order: 0, version: 1, created_at: '', updated_at: ''})))
  const w = await duplicateFailure()
  const row = w.findAll('.directory-rule')[0]!
  row.findAllComponents({ name: 'ElSelect' })[0]!.vm.$emit('update:modelValue', 'train')
  w.findAllComponents({ name: 'ElInputNumber' }).at(-1)!.vm.$emit('update:modelValue', 42)
  await w.get('[data-test="manual-mode"] input').setValue(true)
  await w.get('[data-test="label-enabled-helmet"]').trigger('click')
  await w.get('[data-test="move-up-car"]').trigger('click')
  vi.mocked(previewDatasetExport).mockRejectedValueOnce(new Error('重复图固定划分冲突'))
  await vi.advanceTimersByTimeAsync(250); await flushPromises()
  const before = JSON.parse(JSON.stringify(vi.mocked(previewDatasetExport).mock.calls.at(-1)![1]))
  const directoriesBefore = vi.mocked(listImageDirectories).mock.calls.length
  vi.mocked(previewDatasetExport).mockResolvedValue(preview('after-disable'))
  await w.get('[data-test="disable-duplicate-images"]').trigger('click'); await flushPromises()
  expect(previewImageDuplicates).toHaveBeenCalledWith('image-project')
  expect(ElMessageBox.confirm).toHaveBeenCalledWith(expect.stringContaining('项目内当前启用图像'), '确认停用重复图像', expect.objectContaining({ cancelButtonText: '取消' }))
  const message = vi.mocked(ElMessageBox.confirm).mock.calls[0]![0] as string
  for (const text of ['1 组', '2 张', '稳定保留首张', '不删除图像或标注', '不启用已停用图像', '整个项目']) expect(message).toContain(text)
  expect(disableDuplicateImages).toHaveBeenCalledWith('image-project', 'duplicates-current')
  expect(listImageDirectories).toHaveBeenCalledTimes(directoriesBefore + 1)
  expect(w.emitted('source-updated')).toHaveLength(1)
  expect(w.get('[data-test="dataset-name"]').element).toHaveProperty('value', '图片快照')
  expect(vi.mocked(previewDatasetExport).mock.calls.at(-1)![1]).toEqual({ ...before, name: '图片快照' })
  await w.get('[data-test="submit-export"]').trigger('click'); await flushPromises()
  expect(createDatasetExport).toHaveBeenCalledWith('image-project', { ...before, name: '图片快照', preview_fingerprint: 'after-disable' })
})

it('does not write or refresh sources when duplicate confirmation is cancelled', async () => {
  const w = await duplicateFailure()
  vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
  const count = vi.mocked(listImageDirectories).mock.calls.length
  await w.get('[data-test="disable-duplicate-images"]').trigger('click'); await flushPromises()
  expect(disableDuplicateImages).not.toHaveBeenCalled()
  expect(listImageDirectories).toHaveBeenCalledTimes(count)
  expect(w.emitted('source-updated')).toBeUndefined()
  expect(w.get('[data-test="disable-duplicate-images"]').attributes('disabled')).toBeUndefined()
})

it.each(['read', 'write'])('keeps errors visible and retries duplicates with a fresh fingerprint after %s failure', async phase => {
  const w = await duplicateFailure()
  if (phase === 'read') vi.mocked(previewImageDuplicates).mockRejectedValueOnce(new Error('无法读取重复组'))
  else vi.mocked(disableDuplicateImages).mockRejectedValueOnce(new Error('指纹已变化，请重试'))
  await w.get('[data-test="disable-duplicate-images"]').trigger('click'); await flushPromises()
  expect(w.text()).toContain(phase === 'read' ? '无法读取重复组' : '指纹已变化，请重试')
  expect(w.emitted('source-updated')).toBeUndefined()
  vi.mocked(previewImageDuplicates).mockResolvedValueOnce({ fingerprint: 'fresh', group_count: 1, duplicate_count: 1, groups: [] })
  await w.get('[data-test="disable-duplicate-images"]').trigger('click'); await flushPromises()
  expect(disableDuplicateImages).toHaveBeenLastCalledWith('image-project', 'fresh')
  expect(w.emitted('source-updated')).toHaveLength(1)
})

it('discards duplicate preview responses after changing projects before confirmation', async () => {
  const w = await duplicateFailure()
  let finish!: (value: Awaited<ReturnType<typeof previewImageDuplicates>>) => void
  const value = { fingerprint: 'obsolete', group_count: 1, duplicate_count: 1, groups: [] }
  vi.mocked(previewImageDuplicates).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  await w.get('[data-test="disable-duplicate-images"]').trigger('click')
  await w.setProps({ projectId: 'other-project' }); await flushPromises()
  finish(value); await flushPromises()
  expect(ElMessageBox.confirm).not.toHaveBeenCalled()
  expect(disableDuplicateImages).not.toHaveBeenCalled()
})

it('shows actual and target strata by selected classes, including opposite deviations when the total matches', async () => {
  vi.mocked(previewDatasetExport).mockResolvedValue({
    ...preview(), total_samples: 4, train_samples: 2, val_samples: 2, actual_train_ratio: 0.5,
    positive_samples: { train: 2, val: 0 }, negative_samples: { train: 0, val: 2 },
    target_positive_samples: { train: 1, val: 1 }, target_negative_samples: { train: 1, val: 1 },
    positive_deviation: 1, negative_deviation: -1,
    directory_stats: [{ directory_id: 'train', name: 'train', source_relative_path: 'images/train',
      total_images: 4, effective_images: 4, train_images: 2, val_images: 2, target_train_images: 2, deviation: 0,
      positive_images: 2, negative_images: 2, train_positive_images: 2, val_positive_images: 0,
      train_negative_images: 0, val_negative_images: 2,
      target_train_positive_images: 1, target_val_positive_images: 1,
      target_train_negative_images: 1, target_val_negative_images: 1,
      positive_deviation: 1, negative_deviation: -1, positive_deviation_reason: 'exact_content_groups', negative_deviation_reason: 'exact_content_groups', deviation_reason: 'exact_content_groups', excluded: {},
      rule: { directory_id: 'train', included: true, mode: 'ratio', train_ratio: null },
    }],
  })
  const w = await open()
  expect(w.get('[data-test="image-export-strata"]').text()).toContain('正样本：训练 2 / 目标 1，验证 0 / 目标 1')
  expect(w.get('[data-test="image-export-strata"]').text()).toContain('负样本：训练 0 / 目标 1，验证 2 / 目标 1')
  expect(w.get('.directory-stat').text()).toContain('正样本 1，负样本 -1')
  expect(w.get('[data-test="image-export-preview"]').text()).not.toContain('排除：待标注')
  const hint = w.get('[data-test="image-export-negative-hint"]').text()
  for (const text of ['无目标框', '包括尚未标注图片', '导出为负样本', '先补标注', '停用图片 / 排除目录']) expect(hint).toContain(text)
  expect(w.text()).toContain('按本次保留类别统计并分别划分')
})

it('reports an outdated preview contract instead of rendering missing strata or allowing export', async () => {
  const value = { ...preview() }
  Reflect.deleteProperty(value, 'positive_samples')
  vi.mocked(previewDatasetExport).mockResolvedValue(value)
  const w = await open()
  expect(w.text()).toContain('服务端未返回正负样本划分统计')
  expect(w.get('[data-test="submit-export"]').attributes('disabled')).toBeDefined()
  expect(w.find('[data-test="image-export-strata"]').exists()).toBe(false)
})

it('explains insufficient strata even when the rounded targets have no deviation', async () => {
  vi.mocked(previewDatasetExport).mockResolvedValue({ ...preview(), stratification_warnings: [
    { directory_id: 'train', kind: 'positive', reason: 'insufficient_samples' },
    { directory_id: 'val', kind: 'negative', reason: 'fixed_roles' },
    { directory_id: 'default', kind: 'negative', reason: 'exact_content_groups' },
  ] })
  const w = await open()
  expect(w.findAll('.split-warning').map(row => row.text())).toEqual([
    'train：正样本不足两张，无法同时分配训练集和验证集。',
    'val：负样本受固定目录规则约束。',
    'default：负样本受重复图像不可拆分约束。',
  ])
})

it('can refresh directory metadata after duplicates were disabled but the source reload failed', async () => {
  const w = await duplicateFailure()
  vi.mocked(listImageDirectories).mockRejectedValueOnce(new Error('目录刷新失败'))
  await w.get('[data-test="disable-duplicate-images"]').trigger('click'); await flushPromises()
  expect(w.emitted('source-updated')).toHaveLength(1)
  expect(w.text()).toContain('目录刷新失败')
  const writes = vi.mocked(disableDuplicateImages).mock.calls.length
  const reads = vi.mocked(listImageDirectories).mock.calls.length
  vi.mocked(previewImageDuplicates).mockResolvedValueOnce({fingerprint: 'clean', group_count: 0, duplicate_count: 0, groups: []})
  await w.get('[data-test="disable-duplicate-images"]').trigger('click'); await flushPromises()
  expect(listImageDirectories).toHaveBeenCalledTimes(reads + 1)
  expect(disableDuplicateImages).toHaveBeenCalledTimes(writes)
  expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1)
  expect(w.text()).not.toContain('目录刷新失败')
})
