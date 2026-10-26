import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { getImage, imageNeighbors, listImageDirectories, listImages, setImagesEnabled, deleteImages, setImagesEnabledByAnnotations, type ImageAsset, type ImagePage } from '../api/images'
import { listTasks } from '../api/media'
import { listLabels } from '../api/labels'
import { notify } from '../ui/notify'
import type { Project } from '../api/projects'
import ProjectImagesView from './ProjectImagesView.vue'
import ImagePreviewDialog from '../components/ImagePreviewDialog.vue'
import VButton from '../ui/VButton.vue'

const { push } = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('vue-router', () => ({ RouterView: { template: '<div/>' }, useRoute: () => ({ name: 'project-images', params: { id: 'project-id' } }), useRouter: () => ({ push }) }))
vi.mock('../api/images', async original => ({ ...await original<typeof import('../api/images')>(), getImage: vi.fn(), imageNeighbors: vi.fn(), listImageDirectories: vi.fn(), listImages: vi.fn(), setImagesEnabled: vi.fn(), deleteImages: vi.fn(), setImagesEnabledByAnnotations: vi.fn() }))
vi.mock('../api/media', () => ({ listTasks: vi.fn() }))
vi.mock('../api/labels', () => ({ listLabels: vi.fn() }))
vi.mock('../ui/notify', () => ({ notify: { error: vi.fn(), warning: vi.fn(), info: vi.fn(), success: vi.fn() } }))
const project: Project = { id: 'project-id', project_type: 'image', name: '图片集', description: '', creator_id: 'user', creator_username: 'user', categories: [], access: { role: 'owner', source: 'owner', permissions: ['project.read', 'project.update', 'task.execute'] }, version: 1, created_at: '', updated_at: '' }
const image = (id: string, extra: Partial<ImageAsset> = {}): ImageAsset => ({ id, file_name: `${id}.jpg`, source_relative_path: `${id}.jpg`, directory_id: 'directory', width: 640, height: 480, file_size: 100, content_sha256: id, materialization: 'copy', enabled: true, annotation_status: 'pending', annotation_revision: 3, version: 2, annotations: [], created_at: '', updated_at: '', ...extra })
const images = [image('a'), image('b'), image('c')]
const page = (items = images): ImagePage => ({ items, total: 101, page: 1, page_size: 50, summary:{enabled_images:100,labeled_images:50} })
const wrappers: ReturnType<typeof mount>[] = []
const button = (w: ReturnType<typeof mount>, text: string) => w.findAllComponents(VButton).find(b => b.text() === text)!
beforeEach(() => {
  vi.resetAllMocks(); vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  vi.mocked(listImages).mockResolvedValue(page())
  vi.mocked(imageNeighbors).mockResolvedValue({previous_id:null,next_id:'next-page'})
  vi.mocked(getImage).mockResolvedValue(image('next-page'))
  vi.mocked(listImageDirectories).mockResolvedValue([{ id: 'directory', name: 'test', import_id: 'batch', source_relative_path: 'images/test', total_images: 101, enabled_images: 100, labeled_images: 50, min_width: 640, max_width: 640, min_height: 480, max_height: 480 }])
  vi.mocked(listLabels).mockResolvedValue([])
  vi.mocked(listTasks).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })
})
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.useRealTimers(); vi.restoreAllMocks() })
async function open(value: Project = project) {
  const w = mount(ProjectImagesView, { props: { project: value }, global: { plugins: [ElementPlus], directives: { loading: () => {} }, stubs: { ElOption: true, ElSelect: { name: 'ElSelect', props: ['modelValue'], emits: ['update:modelValue'], template: '<div><slot/></div>' }, ImportImagesDialog: true, ExportDatasetDialog: true, BatchAnnotationDialog: true, ImagePreviewDialog: true, ImageScreeningDialog: true, FrameAnnotationThumbnail: true, Teleport: true } } })
  wrappers.push(w); await flushPromises(); return w
}

it('loads only one server page and keeps current-page range selection', async () => {
  const w = await open()
  expect(w.element.tagName.toLowerCase()).toBe('main')
  expect(listImages).toHaveBeenCalledWith('project-id', expect.any(Object), 1, 50)
  expect(w.findAll('.image-card')).toHaveLength(3)
  await w.get('input[aria-label="选择 a.jpg"]').trigger('click')
  await w.get('input[aria-label="选择 c.jpg"]').trigger('click', { shiftKey: true })
  expect(w.findAll('.image-card.selected')).toHaveLength(3)
  w.getComponent({ name: 'ElPagination' }).vm.$emit('current-change', 2)
  await flushPromises()
  expect(listImages).toHaveBeenLastCalledWith('project-id', expect.any(Object), 2, 50)
  expect(w.findAll('.image-card.selected')).toHaveLength(0)
  w.getComponent({ name: 'ElPagination' }).vm.$emit('update:pageSize', 100)
  await flushPromises()
  expect(listImages).toHaveBeenLastCalledWith('project-id', expect.any(Object), 1, 100)
})

it('resets selection and page for filters and debounces server search', async () => {
  const w = await open()
  await w.get('input[aria-label="选择 a.jpg"]').trigger('click')
  w.findAllComponents({name:'ElSelect'})[0]!.vm.$emit('update:modelValue',['__all__','directory']); await flushPromises()
  expect(listImages).toHaveBeenLastCalledWith('project-id', expect.objectContaining({ directory_id: ['directory'] }), 1, 50)
  expect(w.findAll('.image-card.selected')).toHaveLength(0)
  const calls = vi.mocked(listImages).mock.calls.length
  await w.get('input[aria-label="搜索文件名"]').setValue('a')
  await w.get('input[aria-label="搜索文件名"]').setValue('ab')
  expect(listImages).toHaveBeenCalledTimes(calls)
  await vi.advanceTimersByTimeAsync(250); await flushPromises()
  expect(listImages).toHaveBeenCalledTimes(calls + 1)
  expect(listImages).toHaveBeenLastCalledWith('project-id', expect.objectContaining({ search: 'ab' }), 1, 50)
})

it('ignores an older page response after a filter change', async () => {
  let finish!: (value: ImagePage) => void
  vi.mocked(listImages).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  const w = await open()
  w.findAllComponents({ name: 'ElSelect' })[1]!.vm.$emit('update:modelValue', 'pending'); await flushPromises()
  expect(w.text()).toContain('a.jpg')
  finish(page([image('obsolete')])); await flushPromises()
  expect(w.text()).not.toContain('obsolete.jpg')
})

it('retries a failed load and retains selected items when a batch write fails', async () => {
  vi.mocked(listImages).mockRejectedValueOnce(new Error('图片列表失败'))
  const w = await open()
  expect(w.text()).toContain('图片列表失败')
  expect(w.findComponent({name: 'ElEmpty'}).exists()).toBe(false)
  await button(w, '重试加载').trigger('click'); await flushPromises()
  await w.get('input[aria-label="选择 a.jpg"]').trigger('click')
  vi.mocked(setImagesEnabled).mockRejectedValueOnce(new Error('版本冲突'))
  await button(w, '停用').trigger('click'); await flushPromises()
  expect(setImagesEnabled).toHaveBeenCalledWith('project-id', [{ image_id: 'a', version: 2, enabled: false }])
  expect(notify.error).toHaveBeenCalledWith('版本冲突')
  expect(w.findAll('.image-card.selected')).toHaveLength(1)
})

it('unifies toolbar states, offers screening and shows class/object counts without resolution', async () => {
  const w = await open()
  const lane = w.get('.image-action-lane')
  expect(lane.findAll('button').map(b=>b.text())).toEqual(['标注','筛选','导出数据集','导入图像目录'])
  expect(lane.find('input[aria-label="搜索文件名"]').exists()).toBe(false)
  expect(w.find('.image-filters input[aria-label="搜索文件名"]').exists()).toBe(true)
  expect(w.find('.directory-list').exists()).toBe(false)
  expect(w.get('.image-counts').text()).toContain('启用 100 · 已标注 50')
  expect(w.text()).not.toContain('确认无目标')
  expect(w.text()).not.toContain('已选 0 张')
  expect(w.get('.image-card footer').text()).toContain('0 类 · 0 目标')
  expect(w.get('.image-card footer').text()).not.toContain('640')
  await w.get('input[aria-label="选择 a.jpg"]').trigger('click')
  expect(lane.findAll('button').map(b=>b.text())).toEqual(['启用','停用','批量自动标注','按标注启停','删除 0 个图像'])
  expect(button(w,'删除 0 个图像').props('disabled')).toBe(true)
  expect(w.get('.image-counts').text()).toContain('选中 1 · 启用 1 · 已标注 0')
  await w.get('input[aria-label="选择 a.jpg"]').trigger('click')
  await button(w,'筛选').trigger('click')
  expect(w.getComponent({name:'ImageScreeningDialog'}).props('modelValue')).toBe(true)
})

it('deletes only stopped images after confirmation with their versions', async () => {
  vi.spyOn(ElMessageBox,'confirm').mockResolvedValue('confirm' as never)
  vi.mocked(listImages).mockResolvedValue(page([image('a'),image('b',{enabled:false})]))
  vi.mocked(deleteImages).mockResolvedValue({deleted:['b']})
  const w = await open()
  expect(w.get('button[aria-label="删除图像 a.jpg"]').attributes('disabled')).toBeDefined()
  await w.get('input[aria-label="选择 a.jpg"]').trigger('click')
  await w.get('input[aria-label="选择 b.jpg"]').trigger('click')
  await button(w,'删除 1 个图像').trigger('click'); await flushPromises()
  expect(deleteImages).toHaveBeenCalledWith('project-id',[{image_id:'b',version:2}])
  expect(ElMessageBox.confirm).toHaveBeenCalled()
})

it('preserves stopped images when delete confirmation is canceled', async () => {
  vi.spyOn(ElMessageBox,'confirm').mockRejectedValue('cancel')
  vi.mocked(listImages).mockResolvedValue(page([image('a',{enabled:false})]))
  const w = await open()
  await w.get('button[aria-label="删除图像 a.jpg"]').trigger('click'); await flushPromises()
  expect(deleteImages).not.toHaveBeenCalled()
})

it('applies annotation enablement to the selected versioned images after confirmation', async () => {
  vi.spyOn(ElMessageBox,'confirm').mockResolvedValue('confirm' as never)
  vi.mocked(setImagesEnabledByAnnotations).mockResolvedValue({changes:[]})
  const w = await open()
  await w.get('input[aria-label="选择 a.jpg"]').trigger('click')
  await button(w,'按标注启停').trigger('click'); await flushPromises()
  expect(setImagesEnabledByAnnotations).toHaveBeenCalledWith('project-id',[{image_id:'a',version:2}])
})

it('disables writes for viewers and during an active export', async () => {
  const viewer = await open({ ...project, access: { role: 'viewer', source: 'membership', permissions: ['project.read'] } })
  expect(button(viewer, '导入图像目录').props('disabled')).toBe(true)
  expect(button(viewer, '导出数据集').props('disabled')).toBe(true)
  vi.mocked(listTasks).mockResolvedValue({ items: [{ id: 'export-task', status: 'running', type: 'export_dataset' }] as Awaited<ReturnType<typeof listTasks>>['items'], total: 1, page: 1, page_size: 50 })
  const w = await open()
  expect(w.text()).toContain('图片数据任务正在处理')
  expect(button(w, '导入图像目录').props('disabled')).toBe(true)
  await w.get('input[aria-label="选择 a.jpg"]').trigger('click')
  expect(button(w, '停用').props('disabled')).toBe(true)
})

it('opens a preview and routes to image annotation with the active filters', async () => {
  const w = await open()
  w.findAllComponents({name:'ElSelect'})[0]!.vm.$emit('update:modelValue',['directory']); await flushPromises()
  await w.get('button[aria-label="预览 a.jpg"]').trigger('click')
  const preview = w.getComponent(ImagePreviewDialog)
  expect(preview.props('modelValue')).toBe(true)
  expect(preview.props('directoryName')).toBe('test')
  preview.vm.$emit('annotate', images[0]); await w.vm.$nextTick()
  expect(push).toHaveBeenCalledWith({ path: '/projects/project-id/images/a/annotation', query: { directory_id: ['directory'] }, state: { annotationFromImageList: true } })
  expect(preview.props('modelValue')).toBe(false)
})

it('announces when filtering clears a nonempty selection and offers clearing empty results', async () => {
  const w = await open()
  await w.get('input[aria-label="选择 a.jpg"]').trigger('click')
  vi.mocked(listImages).mockResolvedValue(page([]))
  w.findAllComponents({ name: 'ElSelect' })[1]!.vm.$emit('update:modelValue', 'pending'); await flushPromises()
  expect(notify.info).toHaveBeenCalledWith('筛选已变化，已清空当前页选择。')
  expect(w.text()).toContain('没有匹配的图片')
  await button(w, '清除筛选').trigger('click'); await flushPromises()
  expect(listImages).toHaveBeenLastCalledWith('project-id', expect.objectContaining({ annotation_status: undefined }), 1, 50)
})

it('supports multi-directory filters, all-directory reset and cross-page preview navigation', async()=>{
  const w=await open()
  const directory=w.findAllComponents({name:'ElSelect'})[0]!
  directory.vm.$emit('update:modelValue',['directory','other']);await flushPromises()
  expect(listImages).toHaveBeenLastCalledWith('project-id',expect.objectContaining({directory_id:['directory','other']}),1,50)
  await w.get('button[aria-label="预览 a.jpg"]').trigger('click');await flushPromises()
  const preview=w.getComponent(ImagePreviewDialog)
  expect(preview.props('previousDisabled')).toBe(true)
  expect(preview.props('nextDisabled')).toBe(false)
  preview.vm.$emit('navigate',1);await flushPromises()
  expect(getImage).toHaveBeenCalledWith('project-id','next-page')
  expect(preview.props('image')!.id).toBe('next-page')
  expect(imageNeighbors).toHaveBeenLastCalledWith('project-id','next-page',expect.objectContaining({directory_id:['directory','other']}))
  preview.vm.$emit('update:modelValue',false)
  directory.vm.$emit('update:modelValue',['directory','other','__all__']);await flushPromises()
  expect(listImages).toHaveBeenLastCalledWith('project-id',expect.objectContaining({directory_id:undefined}),1,50)
})
