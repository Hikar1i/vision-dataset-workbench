import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { getTrainingResources, type TrainingResources, type TrainingModelDraft } from '../api/training'
import { getDatasetExport, type DatasetExport } from '../api/datasetExports'
import { notify } from '../ui/notify'
import TrainingTaskEditorView from './TrainingTaskEditorView.vue'
import TrainingModelEditor from '../components/TrainingModelEditor.vue'
import DatasetSelectionSummary from '../components/DatasetSelectionSummary.vue'
import ExportDatasetDialog from '../components/ExportDatasetDialog.vue'
import MultiDatasetMappingDialog from '../components/MultiDatasetMappingDialog.vue'

vi.mock('vue-router', () => ({ useRoute: () => ({ params: {} }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('../api/training', async original => ({ ...await original<typeof import('../api/training')>(), getTrainingCapabilities: vi.fn().mockResolvedValue({ devices: [], training_available: false }), getTrainingResources: vi.fn() }))
vi.mock('../api/hyperparameters', async original => ({ ...await original<typeof import('../api/hyperparameters')>(), getHyperparameterCatalog: vi.fn().mockResolvedValue({ items: [] }) }))
vi.mock('../api/datasetExports', () => ({ getDatasetExport: vi.fn() }))
vi.mock('../ui/notify', () => ({ notify: { info: vi.fn(), error: vi.fn(), warning: vi.fn() } }))
const dataset = (id: string): TrainingResources['datasets'][number] => ({ id, name: id, project_id: 'image-project', project_name: '图片集', project_type: 'image', total_samples: 10, train_samples: 8, val_samples: 2, total_frames: 10, train_frames: 8, val_frames: 2, labels: [{ index: 0, name: 'helmet' }] })
const resources = (): TrainingResources => ({ image_projects: [{ id: 'image-project', name: '图片集', can_export: true, total_images: 10 }], datasets: [dataset('old'), dataset('other')], templates: [], base_models: [] })
const exported = (status: DatasetExport['status'] = 'queued'): DatasetExport => ({ id: 'new', project_id: 'image-project', task_id: 'export-task', project_type: 'image', name: '新快照', status, error: status === 'failed' ? '导出失败' : null, train_ratio: 0.8, actual_train_ratio: null, total_samples: 10, train_samples: 8, val_samples: 2, total_frames: 10, train_frames: 8, val_frames: 2, total_videos: null, train_videos: null, val_videos: null, labels: [{ source_label_id: 'helmet', name: 'helmet', mapping: 0, enabled: true }], created_at: '', started_at: null, completed_at: null })
const wrappers: VueWrapper[] = []
beforeEach(() => {
  vi.clearAllMocks(); vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  vi.mocked(getTrainingResources).mockReset().mockResolvedValue(resources())
  vi.mocked(getDatasetExport).mockReset().mockResolvedValue({ ...exported(), absolute_path: null, manifest: null })
})
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.useRealTimers() })
async function open() {
  const w = shallowMount(TrainingTaskEditorView, { global: { renderStubDefaultSlot: true, directives: { loading: () => {} }, stubs: {
    VButton: false,
    ElDialog: { props: ['modelValue', 'title'], template: '<section v-if="modelValue" class="dialog"><h3>{{ title }}</h3><slot/></section>' },
    ElForm: { template: '<div><slot/></div>' }, ElFormItem: { template: '<div><slot/></div>' },
    ElSegmented: { name: 'ElSegmented', props: ['modelValue', 'options'], emits: ['update:modelValue'], template: '<div/>' },
    ElCascader: { name: 'ElCascader', props: ['modelValue', 'options'], emits: ['update:modelValue'], template: '<div/>' },
    ElSelect: true, ElOption: true, ElInput: true, ElAlert: true, ElSwitch: true,
  } } })
  wrappers.push(w); await flushPromises()
  expect(notify.error).not.toHaveBeenCalled()
  w.getComponent({ name: 'ElCascader' }).vm.$emit('update:modelValue', 'old'); await nextTick()
  return w
}
const summary = (w: VueWrapper) => w.getComponent(DatasetSelectionSummary)
const models = (w: VueWrapper): TrainingModelDraft[] => w.getComponent(TrainingModelEditor).props('models')
async function start(w: VueWrapper, model?: TrainingModelDraft) {
  if (model) { w.getComponent(TrainingModelEditor).vm.$emit('create-snapshot', model); await nextTick() }
  else { await w.findAll('button').find(b => b.text() === '从图像项目创建快照')!.trigger('click') }
  await w.findAll('button').find(b => b.text() === '选择当前状态')!.trigger('click')
  return w.getComponent(ExportDatasetDialog)
}
async function queue(w: VueWrapper, model?: TrainingModelDraft) {
  const dialog = await start(w, model)
  dialog.vm.$emit('submitted', exported()); dialog.vm.$emit('update:modelValue', false); await nextTick()
}
async function ready() {
  vi.mocked(getTrainingResources).mockResolvedValue({ ...resources(), datasets: [...resources().datasets, dataset('new')] })
  vi.mocked(getDatasetExport).mockResolvedValue({ ...exported('ready'), absolute_path: null, manifest: null })
  await vi.advanceTimersByTimeAsync(1500); await flushPromises()
}

it('keeps the old default until ready and refreshes resources before selecting the export', async () => {
  const w = await open(); await queue(w)
  expect(summary(w).props('datasetId')).toBe('old')
  await vi.advanceTimersByTimeAsync(1500); await flushPromises()
  expect(summary(w).props('datasetId')).toBe('old')
  await ready()
  expect(getTrainingResources).toHaveBeenCalledTimes(2)
  expect(summary(w).props('datasetId')).toBe('new')
  expect(vi.getTimerCount()).toBe(0)
})

it.each(['failed', 'canceled'] as const)('preserves input after %s and stops polling', async status => {
  const w = await open(); await queue(w)
  vi.mocked(getDatasetExport).mockResolvedValue({ ...exported(status), absolute_path: null, manifest: null })
  await vi.advanceTimersByTimeAsync(1500); await flushPromises()
  expect(summary(w).props('datasetId')).toBe('old')
  expect(getTrainingResources).toHaveBeenCalledTimes(1)
  expect(vi.getTimerCount()).toBe(0)
  if (status === 'failed') expect(notify.error).toHaveBeenCalledWith('导出失败')
})

it('canceling before submission creates no poll or dataset selection change', async () => {
  const w = await open(); const dialog = await start(w)
  dialog.vm.$emit('update:modelValue', false); await nextTick()
  await vi.advanceTimersByTimeAsync(3000)
  expect(getDatasetExport).not.toHaveBeenCalled()
  expect(summary(w).props('datasetId')).toBe('old')
})

it('never restores autofill eligibility after changing selection and changing it back', async () => {
  const w = await open(); await queue(w)
  const select = w.getComponent({ name: 'ElCascader' })
  select.vm.$emit('update:modelValue', 'other')
  select.vm.$emit('update:modelValue', 'old'); await nextTick()
  await ready()
  expect(summary(w).props('datasetId')).toBe('old')
  expect(notify.info).toHaveBeenLastCalledWith(expect.stringContaining('手动选择'))
})

it('leaves inherited input until ready then applies an explicit model override', async () => {
  const w = await open(); const target = models(w)[0]!
  expect(target.dataset_mode).toBe('inherit')
  await queue(w, target)
  expect(target.dataset_mode).toBe('inherit')
  await ready()
  expect(target.dataset_mode).toBe('single')
  expect(target.dataset_export_id).toBe('new')
  expect(summary(w).props('datasetId')).toBe('old')
})

it('does not apply to another row when the initiating model was deleted', async () => {
  const w = await open(); const target = models(w)[0]!
  await queue(w, target)
  const other = { ...target, name: '另一模型' }
  w.getComponent(TrainingModelEditor).vm.$emit('change', [other]); await nextTick()
  await ready()
  expect(models(w)[0]?.dataset_export_id).toBeNull()
  expect(summary(w).props('datasetId')).toBe('old')
})

it('keeps model identity after reordering and ignores model selection changes', async () => {
  const w = await open(); const target = models(w)[0]!
  const other = { ...target, name: '另一模型' }
  w.getComponent(TrainingModelEditor).vm.$emit('change', [target, other]); await nextTick()
  await queue(w, target)
  w.getComponent(TrainingModelEditor).vm.$emit('change', [models(w)[1], target]); await nextTick()
  await ready()
  expect(models(w)[1]).toBe(target)
  expect(target.dataset_export_id).toBe('new')
  expect(models(w)[0]?.dataset_export_id).toBeNull()
})

it('keeps a ready export unselected if consumption permissions changed', async () => {
  const w = await open(); await queue(w)
  vi.mocked(getDatasetExport).mockResolvedValue({ ...exported('ready'), absolute_path: null, manifest: null })
  await vi.advanceTimersByTimeAsync(1500); await flushPromises()
  expect(summary(w).props('datasetId')).toBe('old')
  expect(notify.info).toHaveBeenLastCalledWith(expect.stringContaining('手动选择'))
})

it('preserves input when resource refresh fails', async () => {
  const w = await open(); await queue(w)
  vi.mocked(getTrainingResources).mockRejectedValueOnce(new Error('资源刷新失败'))
  vi.mocked(getDatasetExport).mockResolvedValue({ ...exported('ready'), absolute_path: null, manifest: null })
  await vi.advanceTimersByTimeAsync(1500); await flushPromises()
  expect(summary(w).props('datasetId')).toBe('old')
  expect(notify.error).toHaveBeenCalledWith('资源刷新失败')
})

it('stops polling on unmount and refuses a ready response already in flight', async () => {
  let finish!: (value: Awaited<ReturnType<typeof getDatasetExport>>) => void
  const w = await open(); const target = models(w)[0]!; await queue(w, target)
  vi.mocked(getDatasetExport).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  await vi.advanceTimersByTimeAsync(1500)
  w.unmount(); wrappers.splice(wrappers.indexOf(w), 1)
  finish({ ...exported('ready'), absolute_path: null, manifest: null }); await flushPromises()
  expect(target.dataset_mode).toBe('inherit')
  expect(getTrainingResources).toHaveBeenCalledTimes(1)
  expect(vi.getTimerCount()).toBe(0)
})

it.each(['save', 'cancel'] as const)('requires multi mapping confirmation (%s) before changing inputs', async action => {
  const w = await open()
  w.findAllComponents({ name: 'ElSegmented' })[0]!.vm.$emit('update:modelValue', 'multi'); await nextTick()
  const mapping = w.getComponent(MultiDatasetMappingDialog)
  const original = { version: 1 as const, dataset_export_ids: ['old'], target_classes: ['helmet'] }
  mapping.vm.$emit('save', original); mapping.vm.$emit('update:modelValue', false); await nextTick()
  await queue(w); await ready()
  expect(mapping.props('modelValue')).toBe(true)
  expect(mapping.props('config')).toEqual({ ...original, dataset_export_ids: ['old', 'new'] })
  expect(summary(w).props('config')).toEqual(original)
  if (action === 'save') mapping.vm.$emit('save', mapping.props('config'))
  mapping.vm.$emit('update:modelValue', false); await nextTick()
  expect(summary(w).props('config')).toEqual({ ...original, dataset_export_ids: action === 'save' ? ['old', 'new'] : ['old'] })
})

it('shows the model target and inheritance change before opening export configuration', async () => {
  const w = await open(); const target = models(w)[0]!
  w.getComponent(TrainingModelEditor).vm.$emit('create-snapshot', target); await nextTick()
  expect(w.get('[data-test="snapshot-target-context"]').text()).toContain('模型“模型 1”')
  expect(w.get('[data-test="snapshot-target-context"]').text()).toContain('退出继承')
  await w.findAll('button').find(b => b.text() === '选择当前状态')!.trigger('click')
  expect(w.getComponent(ExportDatasetDialog).props('context')).toContain('退出继承')
  expect(target.dataset_mode).toBe('inherit')
})

it('retains old model input when its selection changes during export', async () => {
  const w = await open(); const target = models(w)[0]!; await queue(w, target)
  target.dataset_mode = 'single'; target.dataset_export_id = 'other'
  w.getComponent(TrainingModelEditor).vm.$emit('change', models(w)); await nextTick()
  await ready()
  expect(target.dataset_export_id).toBe('other')
})

it('requires a successful refresh even if the export appeared in an earlier resource refresh', async () => {
  const w = await open(); await queue(w)
  vi.mocked(getTrainingResources).mockResolvedValueOnce({ ...resources(), datasets: [...resources().datasets, dataset('new')] })
  window.dispatchEvent(new Event('focus')); await flushPromises()
  vi.mocked(getTrainingResources).mockRejectedValueOnce(new Error('权限读取失败'))
  vi.mocked(getDatasetExport).mockResolvedValue({ ...exported('ready'), absolute_path: null, manifest: null })
  await vi.advanceTimersByTimeAsync(1500); await flushPromises()
  expect(summary(w).props('datasetId')).toBe('old')
  expect(notify.info).toHaveBeenLastCalledWith(expect.stringContaining('手动选择'))
})

it.each(['save', 'cancel'] as const)('adds a ready snapshot to the initiating model only after mapping confirmation (%s)', async action => {
  const w = await open(); const target = models(w)[0]!
  const original = { version: 1 as const, dataset_export_ids: ['old'], target_classes: ['helmet'] }
  target.dataset_mode = 'multi'; target.multi_dataset_config = original; await nextTick()
  await queue(w, target); await ready()
  const mapping = w.getComponent(MultiDatasetMappingDialog)
  expect(mapping.props('title')).toContain('模型 1')
  expect(mapping.props('config')).toEqual({ ...original, dataset_export_ids: ['old', 'new'] })
  expect(target.multi_dataset_config).toEqual(original)
  if (action === 'save') mapping.vm.$emit('save', mapping.props('config'))
  mapping.vm.$emit('update:modelValue', false); await nextTick()
  expect(target.multi_dataset_config?.dataset_export_ids).toEqual(action === 'save' ? ['old', 'new'] : ['old'])
  expect(summary(w).props('datasetId')).toBe('old')
})
