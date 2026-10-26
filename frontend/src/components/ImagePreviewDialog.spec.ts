import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, it } from 'vitest'
import type { ImageAsset } from '../api/images'
import ImagePreviewDialog from './ImagePreviewDialog.vue'
import FrameAnnotationThumbnail from './FrameAnnotationThumbnail.vue'
import VButton from '../ui/VButton.vue'
const image: ImageAsset = { id: 'image-a', directory_id: 'test', file_name: 'a.jpg', source_relative_path: 'test/a.jpg', width: 640, height: 480, file_size: 1024, content_sha256: 'a', materialization: 'copy', enabled: true, annotation_status: 'labeled', annotation_revision: 3, version: 2, annotations: [{ id: 'box', label_id: 'helmet', x_min: 10.1, y_min: 20.2, x_max: 10.4, y_max: 20.6, source: 'import', confidence: null }], created_at: '', updated_at: '' }
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()) })
function open() {
  const w = mount(ImagePreviewDialog, { props: { modelValue: true, projectId: 'project-id', image, directoryName: 'test', labelColors: { helmet: '#16866f' }, canEdit: true, locked: false }, global: { plugins: [ElementPlus], stubs: { ElDialog: { template: '<div><slot/></div>' }, FrameAnnotationThumbnail: true } } })
  wrappers.push(w); return w
}
it('loads the original image on demand and toggles boxes without changing annotations', async () => {
  const w = open(); const thumbnail = w.getComponent(FrameAnnotationThumbnail)
  expect(thumbnail.props('imageUrl')).toBe('/api/v1/projects/project-id/images/image-a/file')
  expect(thumbnail.props('imageWidth')).toBe(640)
  expect(thumbnail.props('annotations')).toEqual(image.annotations)
  await w.get('.el-checkbox input').setValue(false)
  expect(thumbnail.props('annotations')).toEqual([])
  expect(image.annotations).toHaveLength(1)
  await w.get('.el-checkbox input').setValue(true)
  expect(thumbnail.props('annotations')).toEqual(image.annotations)
})
it('shows source details and emits annotation and enablement actions for the same image', async () => {
  const w = open()
  expect(w.text()).toContain('test/a.jpg')
  expect(w.text()).toContain('640 × 480')
  await w.findAllComponents(VButton).find(b => b.text() === '打开标注工作台')!.trigger('click')
  await w.findAllComponents(VButton).find(b => b.text() === '停用图片')!.trigger('click')
  expect(w.emitted('annotate')?.[0]?.[0]).toEqual(image)
  expect(w.emitted('enabled')?.[0]).toEqual([image, false])
})
it('disables writes for a viewer or an active data task and explains negative images', async () => {
  const w = open()
  await w.setProps({ canEdit: false, image: { ...image, annotations: [] } })
  expect(w.text()).toContain('无目标框')
  expect(w.findAllComponents(VButton).every(b => b.props('disabled'))).toBe(true)
  await w.setProps({ canEdit: true, locked: true })
  expect(w.findAllComponents(VButton).every(b => b.props('disabled'))).toBe(true)
})
it('shows a load failure and clears it when another image is selected', async () => {
  const w = open()
  w.getComponent(FrameAnnotationThumbnail).vm.$emit('load-error'); await flushPromises()
  expect(w.text()).toContain('图片加载失败')
  await w.setProps({ image: { ...image, id: 'image-b' } })
  expect(w.text()).not.toContain('图片加载失败')
})
