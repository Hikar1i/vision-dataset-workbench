import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ElMessageBox } from 'element-plus'
import { listImages, setImagesEnabled, type ImageAsset } from '../api/images'
import ImageScreeningDialog from './ImageScreeningDialog.vue'
import FrameAnnotationThumbnail from './FrameAnnotationThumbnail.vue'
import ImagePreviewDialog from './ImagePreviewDialog.vue'
import VButton from '../ui/VButton.vue'

vi.mock('../api/images', async original => ({...await original<typeof import('../api/images')>(), listImages:vi.fn(), setImagesEnabled:vi.fn()}))
vi.mock('../ui/notify', () => ({notify:{success:vi.fn()}}))
const image = (id: string, enabled = true): ImageAsset => ({id, directory_id:'dir', file_name:`${id}.jpg`, source_relative_path:`images/${id}.jpg`, content_sha256:id, width:640, height:480, file_size:100, materialization:'copy', enabled, annotation_status:'pending', annotation_revision:1, version:2, annotations:[], created_at:'', updated_at:''})
const all = [image('a'),image('b',false),image('c')]
const wrappers: VueWrapper[] = []
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(listImages).mockResolvedValue({items:all,total:all.length,page:1,page_size:200})
  vi.spyOn(ElMessageBox,'confirm').mockResolvedValue('confirm' as never)
})
afterEach(() => {wrappers.splice(0).forEach(wrapper=>wrapper.unmount()); vi.restoreAllMocks()})
async function open(extra = {}) {
  const wrapper = mount(ImageScreeningDialog, {props:{modelValue:true, projectId:'project', projectName:'Images', filters:{directory_id:'dir'}, directories:[], canEdit:true, locked:false, labelColors:{}, ...extra}, global:{stubs:{
    ElDialog:{props:['modelValue'],template:'<section v-if="modelValue"><slot name="header"/><slot/><slot name="footer"/></section>'},
    ElSelect:true, ElOption:true, ElSwitch:true, ElSlider:true, ElPagination:true, ElInputNumber:true, ElCheckbox:true, ElIcon:true,
    FrameAnnotationThumbnail:true, ImagePreviewDialog:true,
  }}})
  wrappers.push(wrapper); await flushPromises(); return wrapper
}
const button = (wrapper: VueWrapper,text: string) => wrapper.findAllComponents(VButton).find(value=>value.text()===text)!

it('loads matching images with server pages and keeps image identity in thumbnails', async () => {
  vi.mocked(listImages).mockResolvedValueOnce({items:[all[0]!],total:3,page:1,page_size:200})
  const failed = await open()
  expect(failed.text()).toContain('图片范围已变化')
  failed.unmount()
  vi.mocked(listImages).mockResolvedValue({items:all,total:3,page:1,page_size:200})
  const wrapper = await open()
  expect(listImages).toHaveBeenLastCalledWith('project',{directory_id:'dir'},1,200)
  expect(wrapper.findAll('.screen-card')).toHaveLength(3)
  expect(wrapper.getComponent(FrameAnnotationThumbnail).props('sequence')).toBeUndefined()
  expect(wrapper.get('.disabled-text').text()).toBe('1')
})

it('keeps enablement in a draft and only writes versioned differences when saving', async () => {
  const wrapper = await open()
  await button(wrapper,'停用').trigger('click')
  expect(wrapper.get('.pending-text').text()).toBe('1')
  expect(setImagesEnabled).not.toHaveBeenCalled()
  vi.mocked(setImagesEnabled).mockResolvedValue([{id:'a',version:3,enabled:false}])
  await button(wrapper,'保存更改').trigger('click'); await flushPromises()
  expect(setImagesEnabled).toHaveBeenCalledWith('project',[{image_id:'a',version:2,enabled:false}])
  expect(wrapper.get('.pending-text').text()).toBe('0')
  expect(wrapper.emitted('updated')).toHaveLength(1)
})

it('retains the draft when saving conflicts and refuses writes while locked', async () => {
  const wrapper = await open()
  await button(wrapper,'停用').trigger('click')
  vi.mocked(setImagesEnabled).mockRejectedValue(new Error('image version conflict'))
  await button(wrapper,'保存更改').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('image version conflict')
  expect(wrapper.get('.pending-text').text()).toBe('1')
  await wrapper.setProps({locked:true})
  expect(button(wrapper,'保存更改').props('disabled')).toBe(true)
  expect(wrapper.text()).toContain('启停草稿保留')
})

it('requires an explicit discard before closing with unsaved edits', async () => {
  const wrapper = await open()
  await button(wrapper,'停用').trigger('click')
  vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
  await wrapper.get('button[aria-label="关闭图像筛选工作台"]').trigger('click'); await flushPromises()
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  await wrapper.get('button[aria-label="关闭图像筛选工作台"]').trigger('click'); await flushPromises()
  expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
})

it('range-selects images and applies annotation enablement as an unsaved draft', async () => {
  const wrapper = await open()
  await button(wrapper,'范围多选').trigger('click')
  await wrapper.get('button[aria-label="选择 a.jpg"]').trigger('click')
  await wrapper.get('button[aria-label="选择 c.jpg"]').trigger('click',{shiftKey:true})
  expect(wrapper.findAll('.screen-card.selected')).toHaveLength(3)
  expect(wrapper.findAll('.screen-selection')).toHaveLength(3)
  await button(wrapper,'按标注启停').trigger('click'); await flushPromises()
  expect(wrapper.get('.pending-text').text()).toBe('2')
  expect(setImagesEnabled).not.toHaveBeenCalled()
})

it('lets viewers preview images while keeping all editing controls disabled', async () => {
  const wrapper = await open({canEdit:false})
  expect(button(wrapper,'范围多选').props('disabled')).toBe(true)
  expect(button(wrapper,'保存更改').props('disabled')).toBe(true)
  await wrapper.get('button[aria-label="预览 a.jpg"]').trigger('click')
  expect(wrapper.getComponent(ImagePreviewDialog).props('modelValue')).toBe(true)
  expect(wrapper.getComponent(ImagePreviewDialog).props('showAnnotationAction')).toBe(false)
})

it('only applies annotation enablement to selected images and preserves other edits', async () => {
  const wrapper = await open()
  await button(wrapper,'启用').trigger('click')
  await button(wrapper,'范围多选').trigger('click')
  expect(button(wrapper,'按标注启停').props('disabled')).toBe(true)
  await wrapper.get('button[aria-label="选择 a.jpg"]').trigger('click')
  await button(wrapper,'按标注启停').trigger('click'); await flushPromises()
  expect(ElMessageBox.confirm).toHaveBeenCalledWith(expect.stringContaining('选中的 1 张图片'),expect.anything(),expect.anything())
  vi.mocked(setImagesEnabled).mockResolvedValue([{id:'a',version:3,enabled:false},{id:'b',version:3,enabled:true}])
  await button(wrapper,'保存更改').trigger('click'); await flushPromises()
  expect(setImagesEnabled).toHaveBeenCalledWith('project',[
    {image_id:'a',version:2,enabled:false}, {image_id:'b',version:2,enabled:true},
  ])
})

it('ignores stale pages after the dialog is closed', async () => {
  let resolve!: (value: Awaited<ReturnType<typeof listImages>>) => void
  vi.mocked(listImages).mockReturnValueOnce(new Promise(value=>{resolve=value}))
  const wrapper = await open()
  await wrapper.setProps({modelValue:false})
  resolve({items:all,total:3,page:1,page_size:200}); await flushPromises()
  await wrapper.setProps({modelValue:true}); await flushPromises()
  expect(wrapper.findAll('.screen-card')).toHaveLength(3)
  expect(listImages).toHaveBeenCalledTimes(2)
})

it('uses frame-workbench scale and pagination and navigates the full draft range', async()=>{
  const wrapper=await open()
  expect(wrapper.get('.screen-scale output').text()).toBe('1.00×')
  expect(wrapper.get('.screen-pagination').text()).toContain('第 1 / 1 页 · 共 3 张')
  await wrapper.get('button[aria-label="预览 a.jpg"]').trigger('click')
  const preview=wrapper.getComponent(ImagePreviewDialog)
  expect(preview.props('previousDisabled')).toBe(true)
  expect(preview.props('nextDisabled')).toBe(false)
  preview.vm.$emit('navigate',1);await flushPromises()
  expect(preview.props('image')!.id).toBe('b')
  expect(preview.props('image')!.enabled).toBe(false)
  expect(preview.props('positionLabel')).toBe('2 / 3')
  preview.vm.$emit('enabled',all[1],true);await flushPromises()
  expect(preview.props('image')!.enabled).toBe(true)
  expect(setImagesEnabled).not.toHaveBeenCalled()
})
