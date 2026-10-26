import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { importImages, previewImageImport, type ImageImportPreview } from '../api/images'
import { listLabels } from '../api/labels'
import ImportImagesDialog from './ImportImagesDialog.vue'
import ServerFilePicker from './ServerFilePicker.vue'
import VButton from '../ui/VButton.vue'

vi.mock('../api/images', () => ({ importImages: vi.fn(), previewImageImport: vi.fn() }))
vi.mock('../api/labels', () => ({ listLabels: vi.fn() }))
vi.mock('../ui/notify', () => ({ notify: { success: vi.fn() } }))
const wrappers: ReturnType<typeof mount>[] = []
const preview = (extra: Partial<ImageImportPreview> = {}): ImageImportPreview => ({
  format: 'yolo_detect', root_name: 'tiny', fingerprint: 'source-fingerprint', ignored_files: 2,
  total_images: 3, annotation_count: 1, directories: [{ name: 'test', source_relative_path: 'images/test', total_images: 3, labeled_images: 1, annotation_count: 1 }],
  source_classes: [{ source_id: 0, name: ' Helmet ' }], warnings: [], errors: [], ...extra,
})
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(listLabels).mockResolvedValue([{ id: 'helmet', name: 'helmet', description_zh: '', color: '#16866f', enabled: true, sort_order: 0, version: 1, created_at: '', updated_at: '' }])
  vi.mocked(previewImageImport).mockResolvedValue(preview())
})
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); document.body.innerHTML = '' })
async function open() {
  const wrapper = mount(ImportImagesDialog, { props: { modelValue: true, projectId: 'project-id' }, global: { plugins: [ElementPlus], stubs: { ElDialog: { template: '<section><slot/><slot name="footer"/></section>' }, ServerFilePicker: true } } })
  wrappers.push(wrapper); await flushPromises(); return wrapper
}
const button = (w: ReturnType<typeof mount>, text: string) => w.findAllComponents(VButton).find(b => b.text() === text)!

it('loads labels on initial open and maps a normalized source class to the existing label', async () => {
  const w = await open()
  expect(listLabels).toHaveBeenCalledWith('project-id')
  const hint = w.get('[data-test="image-import-negative-hint"]').text()
  for (const text of ['无目标框', '包括尚未标注图片', '导出为负样本', '先补标注', '停用图片 / 排除目录']) expect(hint).toContain(text)
  expect(w.getComponent(ServerFilePicker).props('mode')).toBe('directory')
  w.getComponent(ServerFilePicker).vm.$emit('update:modelValue', 'fixtures/tiny')
  await w.vm.$nextTick()
  await button(w, '预检当前目录').trigger('click'); await flushPromises()
  expect(previewImageImport).toHaveBeenCalledWith('project-id', 'fixtures/tiny', false)
  expect(w.text()).toContain('3 张图片')
  await button(w, '创建导入任务').trigger('click'); await flushPromises()
  expect(importImages).toHaveBeenCalledWith('project-id', { root_path: 'fixtures/tiny', ignore_annotations: false, fingerprint: 'source-fingerprint', confirm_warnings: false, class_mapping: [{ source_id: 0, project_label_id: 'helmet', new_label_name: null }] })
  expect(w.emitted('submitted')).toHaveLength(1)
  expect(w.emitted('update:modelValue')).toContainEqual([false])
})

it('requires warning confirmation and clears it when the selected root changes', async () => {
  vi.mocked(previewImageImport).mockResolvedValue(preview({ warnings: [{ code: 'missing', path: 'test/a.jpg', message: '缺少 TXT' }] }))
  const w = await open()
  await button(w, '预检当前目录').trigger('click'); await flushPromises()
  expect(button(w, '创建导入任务').props('disabled')).toBe(true)
  await w.get('.el-checkbox input').setValue(true)
  expect(button(w, '创建导入任务').props('disabled')).toBe(false)
  await button(w, '创建导入任务').trigger('click'); await flushPromises()
  expect(vi.mocked(importImages).mock.calls[0]?.[1].confirm_warnings).toBe(true)
  w.getComponent(ServerFilePicker).vm.$emit('update:modelValue', 'fixtures/other'); await w.vm.$nextTick()
  expect(button(w, '创建导入任务').props('disabled')).toBe(true)
  expect(w.text()).not.toContain('缺少 TXT')
})

it('blocks source errors and preserves retry feedback after a failed submission', async () => {
  vi.mocked(previewImageImport).mockResolvedValueOnce(preview({ errors: [{ path: 'a.txt:1', message: '类别越界' }] }))
  const w = await open()
  await button(w, '预检当前目录').trigger('click'); await flushPromises()
  expect(w.text()).toContain('a.txt:1：类别越界')
  expect(button(w, '创建导入任务').props('disabled')).toBe(true)
  expect(importImages).not.toHaveBeenCalled()
  await button(w, '预检当前目录').trigger('click'); await flushPromises()
  vi.mocked(importImages).mockRejectedValueOnce(new Error('来源已变化，请重新预检'))
  await button(w, '创建导入任务').trigger('click'); await flushPromises()
  expect(w.text()).toContain('来源已变化，请重新预检')
  expect(w.emitted('submitted')).toBeUndefined()
  expect(button(w, '创建导入任务').props('disabled')).toBe(false)
})

it('discards a preview from a previously selected directory', async () => {
  let finish!: (value: ImageImportPreview) => void
  vi.mocked(previewImageImport).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  const w = await open()
  await button(w, '预检当前目录').trigger('click')
  w.getComponent(ServerFilePicker).vm.$emit('update:modelValue', 'fixtures/other'); await w.vm.$nextTick()
  finish(preview({ root_name: 'obsolete-root' })); await flushPromises()
  expect(w.text()).not.toContain('obsolete-root')
  expect(button(w, '创建导入任务').props('disabled')).toBe(true)
})

it('keeps the original class name visible beside its editable normalized target', async () => {
  vi.mocked(previewImageImport).mockResolvedValue(preview({ source_classes: [{ source_id: 3, name: 'VeryLongOriginalClassNameThatMustRemainReadable' }] }))
  const w = await open()
  await button(w, '预检当前目录').trigger('click'); await flushPromises()
  expect(w.get('.mapping-row>span').text()).toContain('VeryLongOriginalClassNameThatMustRemainReadable')
  expect(w.get('.mapping-row>span').attributes('title')).toBe('VeryLongOriginalClassNameThatMustRemainReadable')
  await button(w, '创建导入任务').trigger('click'); await flushPromises()
  expect(vi.mocked(importImages).mock.calls[0]?.[1].class_mapping).toEqual([{ source_id: 3, project_label_id: null, new_label_name: 'verylongoriginalclassnamethatmustremainreadable' }])
})

it('invalidates the fingerprint and source class mappings when ignoring annotations changes', async () => {
  const w = await open()
  expect(w.findComponent({ name: 'ElRadioGroup' }).exists()).toBe(false)
  expect(w.getComponent({ name: 'ElSwitch' }).props('modelValue')).toBe(false)
  await button(w, '预检当前目录').trigger('click'); await flushPromises()
  expect(w.get('[data-test="resolved-import-format"]').text()).toContain('YOLO 目标检测数据集')
  expect(w.findAll('.mapping-row')).toHaveLength(1)
  w.getComponent({ name: 'ElSwitch' }).vm.$emit('update:modelValue', true); await w.vm.$nextTick()
  expect(button(w, '创建导入任务').props('disabled')).toBe(true)
  expect(w.findAll('.mapping-row')).toHaveLength(0)
  vi.mocked(previewImageImport).mockResolvedValueOnce(preview({ format: 'images', fingerprint: 'images-only', source_classes: [], annotation_count: 0 }))
  await button(w, '预检当前目录').trigger('click'); await flushPromises()
  expect(previewImageImport).toHaveBeenLastCalledWith('project-id', '.', true)
  expect(w.get('[data-test="resolved-import-format"]').text()).toContain('无标注图像目录')
  await button(w, '创建导入任务').trigger('click'); await flushPromises()
  expect(importImages).toHaveBeenCalledWith('project-id', expect.objectContaining({ ignore_annotations: true, fingerprint: 'images-only', class_mapping: [] }))
})

it('clears an older valid preview when a new YOLO inspection fails without falling back', async () => {
  const w = await open()
  await button(w, '预检当前目录').trigger('click'); await flushPromises()
  vi.mocked(previewImageImport).mockRejectedValueOnce(new Error('YOLO 配置损坏'))
  await button(w, '预检当前目录').trigger('click'); await flushPromises()
  expect(w.text()).toContain('YOLO 配置损坏')
  expect(w.findAll('.mapping-row')).toHaveLength(0)
  expect(button(w, '创建导入任务').props('disabled')).toBe(true)
  expect(previewImageImport).toHaveBeenCalledTimes(2)
  expect(importImages).not.toHaveBeenCalled()
})

it('shows skipped content counts and refuses an all-duplicate import', async()=>{
  vi.mocked(previewImageImport).mockResolvedValue(preview({new_images:0,existing_images:2,duplicate_images:1,source_classes:[],annotation_count:0}))
  const w=await open()
  await button(w,'预检当前目录').trigger('click');await flushPromises()
  expect(w.text()).toContain('扫描 3 张图片 · 新增 0 张 · 已存在 2 张 · 批内重复 1 张')
  expect(w.text()).toContain('没有可新增的图片')
  expect(button(w,'创建导入任务').props('disabled')).toBe(true)
  expect(importImages).not.toHaveBeenCalled()
})
