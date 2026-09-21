import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElNotification } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ModelInferenceView from './ModelInferenceView.vue'

const mocks = vi.hoisted(() => ({
  getModel: vi.fn(),
  listArtifacts: vi.fn(),
  getCurrent: vi.fn(),
  listSaved: vi.fn(),
  save: vi.fn(),
  remove: vi.fn(),
}))

vi.mock('../api/models', () => ({
  getInferenceModel: mocks.getModel,
  modelDownloadUrl: (id: string) => `/api/v1/models/${id}/download`,
}))
vi.mock('../api/modelArtifacts', () => ({
  listModelArtifacts: mocks.listArtifacts,
  modelArtifactDownloadUrl: (id: string) => `/api/v1/model-artifacts/${id}/download`,
}))
vi.mock('../api/modelInference', () => ({
  createInference: vi.fn(),
  deleteInference: mocks.remove,
  getCurrentInference: mocks.getCurrent,
  getInference: vi.fn(),
  inferenceFileUrl: (id: string, kind: string) => `/api/v1/model-inference/${id}/files/${kind}`,
  keepInferenceAlive: vi.fn(),
  listSavedInference: mocks.listSaved,
  saveInference: mocks.save,
}))

const source = readFileSync(resolve('src/views/ModelInferenceView.vue'), 'utf8')
const shellStyles = readFileSync(resolve('src/styles/shell.css'), 'utf8')

const currentRun = {
  id: 'current-1', model_id: 'm1', format: 'pt', input_type: 'image', status: 'succeeded',
  parameters: { confidence: 0.25, iou: 0.7, image_size: 640, max_det: 300, stride: 1 },
  statistics: { detections: 2, inference_seconds: 0.3 }, task_id: null, error: null,
  saved_at: null, expires_at: '2026-09-21T00:00:00Z', created_at: '2026-09-20T00:00:00Z',
  started_at: '2026-09-20T00:00:01Z', finished_at: '2026-09-20T00:00:02Z',
}
const savedRun = { ...currentRun, id: 'saved-1', saved_at: '2026-09-20T00:01:00Z', expires_at: null }

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('ModelInferenceView', () => {
  it('keeps one recoverable session with desktop canvas controls and explicit persistence actions', () => {
    expect(source).toContain('会话 24 小时无访问后清理')
    expect(source).toContain('保存推理结果')
    expect(source).toContain('下载源文件')
    expect(source).toContain('下载检测结果')
    expect(source).toContain('5 * 60 * 1000')
    expect(source).toContain('500 * 1024 * 1024')
    expect(source).toContain('20 * 1024 * 1024')
    expect(source).toContain('<template #meta>')
    expect(source).toContain("请先选择图片或视频")
    expect(source).toContain('下载 PyTorch 模型')
    expect(shellStyles).toContain('scrollbar-gutter: stable')
    expect(source).toContain('font: 600 13px var(--vdw-mono)')
    expect(source).not.toContain('inference-advanced-fields')
    expect(source).not.toContain('advanced-toggle')
  })

  it('opens the newly saved result in the visible history workspace', async () => {
    mocks.getModel.mockResolvedValue({
      id: 'm1', name: '模型 1', model_code: 'MODEL-1', status: 'ready', can_manage: true,
      access: {
        role: 'owner', source: 'owner',
        permissions: ['project.read', 'project.update', 'project.members.manage', 'project.delete', 'artifact.read', 'artifact.download', 'artifact.consume', 'task.read', 'task.execute'],
      },
    })
    mocks.listArtifacts.mockResolvedValue([])
    mocks.getCurrent.mockResolvedValue(currentRun)
    mocks.listSaved.mockResolvedValueOnce([]).mockResolvedValue([savedRun])
    mocks.save.mockResolvedValue(savedRun)
    const success = vi.spyOn(ElNotification, 'success').mockReturnValue({ close: vi.fn() } as never)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/model-projects/:id/models', component: { template: '<div />' } },
        { path: '/model-projects/:id/models/:modelId/inference', component: ModelInferenceView },
      ],
    })
    await router.push('/model-projects/p1/models/m1/inference?source=models')
    await router.isReady()
    const wrapper = mount(ModelInferenceView, { attachTo: document.body, global: { plugins: [router, ElementPlus] } })
    await flushPromises()

    await wrapper.get('[data-test="save-inference"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="inference-mode-saved"]').classes()).toContain('active')
    expect(wrapper.get('[data-test="saved-inference-run-saved-1"]').classes()).toContain('active')
    expect(wrapper.get('.inference-stage img').attributes('src')).toContain('/saved-1/files/result')
    expect(wrapper.text()).toContain('下载源文件')
    expect(wrapper.text()).toContain('下载检测结果')
    expect(success).toHaveBeenCalledWith(expect.objectContaining({
      message: '推理结果已保存，可在“已保存结果”中查看。',
      position: 'top-right',
    }))
    wrapper.unmount()
  })
})
