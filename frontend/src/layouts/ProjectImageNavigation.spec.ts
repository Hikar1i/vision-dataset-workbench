import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'
import { afterEach, expect, it, vi } from 'vitest'
import ProjectLayout from './ProjectLayout.vue'
import ProjectImagesView from '../views/ProjectImagesView.vue'

vi.mock('../api/projects', async original => ({...await original<typeof import('../api/projects')>(), getProject:vi.fn().mockResolvedValue({id:'image-project', name:'Images', project_type:'image', access:{permissions:['project.read']}, creator_id:'owner'})}))
vi.mock('../api/images', async original => ({...await original<typeof import('../api/images')>(), listImages:vi.fn().mockResolvedValue({items:[],total:0,page:1,page_size:50}), listImageDirectories:vi.fn().mockResolvedValue([])}))
vi.mock('../api/labels', () => ({listLabels:vi.fn().mockResolvedValue([])}))
vi.mock('../api/media', () => ({listTasks:vi.fn().mockResolvedValue({items:[]})}))
afterEach(() => {document.body.innerHTML=''; vi.unstubAllGlobals()})

it('keeps image content visible when navigating through every project tab with real transitions', async () => {
  vi.stubGlobal('requestAnimationFrame',(callback: FrameRequestCallback)=>window.setTimeout(()=>callback(0),0))
  const router = createRouter({history:createMemoryHistory(), routes:[{path:'/projects/:id',component:ProjectLayout,children:[
    {path:'images',name:'project-images',component:ProjectImagesView},
    ...['labels','datasets','settings'].map(name=>({path:name,name:`project-${name}`,component:{template:`<main data-test="${name}-content">${name}</main>`}})),
  ]}]})
  await router.push('/projects/image-project/images'); await router.isReady()
  const errors: unknown[] = []
  const wrapper = mount({template:'<RouterView/>'},{attachTo:document.body,global:{plugins:[router,ElementPlus],directives:{loading:()=>{}},stubs:{Transition:false, ImportImagesDialog:true, ExportDatasetDialog:true, BatchAnnotationDialog:true, ImagePreviewDialog:true, ImageScreeningDialog:true},config:{errorHandler:error=>errors.push(error)}}})
  try {
    await flushPromises()
    expect(wrapper.find('.image-project-page').exists()).toBe(true)
    for (const name of ['labels','datasets','settings','labels']) {
      await router.push(`/projects/image-project/${name}`); await flushPromises()
      await new Promise(resolve=>setTimeout(resolve,30)); await flushPromises()
      expect(wrapper.find(`[data-test="${name}-content"]`).exists()).toBe(true)
      await router.push('/projects/image-project/images'); await flushPromises()
      await new Promise(resolve=>setTimeout(resolve,30)); await flushPromises()
      expect(wrapper.find('.image-project-page').exists()).toBe(true)
      expect(document.querySelector('#project-page-meta')?.textContent).toContain('张图片')
    }
    expect(errors).toEqual([])
  } finally {wrapper.unmount()}
})
