import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { getTrainingResources, type TrainingResources, type TrainingModelDraft } from '../api/training'
import { notify } from '../ui/notify'
import TrainingTaskEditorView from './TrainingTaskEditorView.vue'
import TrainingModelEditor from '../components/TrainingModelEditor.vue'
import DatasetSelectionSummary from '../components/DatasetSelectionSummary.vue'
import MultiDatasetMappingDialog from '../components/MultiDatasetMappingDialog.vue'

vi.mock('vue-router', () => ({ useRoute: () => ({ params: {} }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('../api/training', async original => ({ ...await original<typeof import('../api/training')>(), getTrainingCapabilities: vi.fn().mockResolvedValue({ devices: [], training_available: false }), getTrainingResources: vi.fn() }))
vi.mock('../api/hyperparameters', async original => ({ ...await original<typeof import('../api/hyperparameters')>(), getHyperparameterCatalog: vi.fn().mockResolvedValue({ items: [] }) }))
vi.mock('../ui/notify', () => ({ notify: { info: vi.fn(), error: vi.fn(), warning: vi.fn() } }))
const dataset = (id: string): TrainingResources['datasets'][number] => ({ id, name: id, project_id: 'image-project', project_name: '图片集', project_type: 'image', total_samples: 10, train_samples: 8, val_samples: 2, total_frames: 10, train_frames: 8, val_frames: 2, labels: [{ index: 0, name: 'helmet' }] })
const resources = (): TrainingResources => ({ image_projects: [{ id: 'image-project', name: '图片集', can_export: true, total_images: 10 }], datasets: [dataset('old'), dataset('other')], templates: [], base_models: [] })
const wrappers: VueWrapper[] = []
beforeEach(() => {
  vi.clearAllMocks(); vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  vi.mocked(getTrainingResources).mockReset().mockResolvedValue(resources())
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

it('uses ready snapshots and exposes no image-project export workflow or polling', async()=>{
  const w=await open()
  expect(w.text()).not.toContain('从图像项目创建快照')
  expect(w.findComponent({name:'ExportDatasetDialog'}).exists()).toBe(false)
  expect(w.findAll('.snapshot-project-row')).toHaveLength(0)
  expect(summary(w).props('datasetId')).toBe('old')
  await vi.advanceTimersByTimeAsync(3000)
  expect(getTrainingResources).toHaveBeenCalledTimes(1)
  expect(vi.getTimerCount()).toBe(0)
})
it('selects existing single datasets without creating exports', async()=>{
  const w=await open()
  w.getComponent({name:'ElCascader'}).vm.$emit('update:modelValue','other');await nextTick()
  expect(summary(w).props('datasetId')).toBe('other')
})
it.each(['save','cancel'] as const)('preserves explicit task multi-dataset mapping (%s)',async action=>{
  const w=await open()
  w.getComponent({name:'ElSegmented'}).vm.$emit('update:modelValue','multi');await nextTick()
  const mapping=w.getComponent(MultiDatasetMappingDialog)
  expect(mapping.props('modelValue')).toBe(true)
  const config={version:1,dataset_export_ids:['old','other'],target_classes:['helmet']}
  if(action==='save')mapping.vm.$emit('save',config)
  mapping.vm.$emit('update:modelValue',false);await nextTick()
  expect(summary(w).props('mode')).toBe(action==='save' ? 'multi':'single')
  expect(summary(w).props('datasetId')).toBe('old')
  expect(summary(w).props('config')).toEqual(action==='save' ? config:null)
})
it('applies model multi-dataset overrides while retaining the task default',async()=>{
  const w=await open()
  const target=models(w)[0]!
  w.getComponent(TrainingModelEditor).vm.$emit('configureMapping',target);await nextTick()
  const config={version:1,dataset_export_ids:['other'],target_classes:['helmet']}
  w.getComponent(MultiDatasetMappingDialog).vm.$emit('save',config);await nextTick()
  expect(target.dataset_mode).toBe('multi')
  expect(target.multi_dataset_config).toEqual(config)
  expect(summary(w).props('datasetId')).toBe('old')
})
it('refreshes available snapshots on focus without changing the selection',async()=>{
  const w=await open()
  vi.mocked(getTrainingResources).mockResolvedValue({...resources(),datasets:[...resources().datasets,dataset('new')]})
  window.dispatchEvent(new Event('focus'));await flushPromises()
  expect(getTrainingResources).toHaveBeenCalledTimes(2)
  expect(summary(w).props('datasetId')).toBe('old')
  w.unmount()
  window.dispatchEvent(new Event('focus'));await flushPromises()
  expect(getTrainingResources).toHaveBeenCalledTimes(2)
})
