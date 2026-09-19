<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, Delete, Download, UploadFilled } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getInferenceModel, modelDownloadUrl, type InferenceModel } from '../api/models'
import { listModelArtifacts, modelArtifactDownloadUrl, type ModelArtifact } from '../api/modelArtifacts'
import {
  createInference,
  deleteInference,
  getCurrentInference,
  getInference,
  inferenceFileUrl,
  keepInferenceAlive,
  listSavedInference,
  saveInference,
  type ModelInferenceRun,
} from '../api/modelInference'
import PageHeader from '../components/PageHeader.vue'
import { modelCapabilityBackTarget } from '../navigation/modelCapabilitySource'
import VButton from '../ui/VButton.vue'
import VPanel from '../ui/VPanel.vue'
import VTag from '../ui/VTag.vue'

const route = useRoute()
const modelId = String(route.params.modelId)
const model = ref<InferenceModel>()
const artifacts = ref<ModelArtifact[]>([])
const current = ref<ModelInferenceRun | null>(null)
const saved = ref<ModelInferenceRun[]>([])
const fileInput = ref<HTMLInputElement>()
const pendingFile = ref<File>()
const view = ref<'source' | 'result'>('result')
const busy = ref(false)
const format = ref<'pt' | 'onnx' | 'engine'>('pt')
const parameters = ref({ confidence: 0.25, iou: 0.7, image_size: 640, max_det: 300, stride: 1 })
let pollTimer: number | undefined
let keepaliveTimer: number | undefined

const formats = computed(() => [
  { value: 'pt' as const, label: 'PyTorch (.pt)', enabled: true, fixed: null as number | null },
  ...artifacts.value.map((item) => ({
    value: item.format,
    label: item.format === 'onnx' ? 'ONNX' : 'TensorRT (.engine)',
    enabled: item.status === 'ready',
    fixed: item.export_config.dynamic ? null : item.export_config.imgsz,
  })),
])
const backTarget = computed(() => modelCapabilityBackTarget(
  String(route.params.id),
  modelId,
  route.query.source,
  { to: `/model-projects/${route.params.id}/models/${modelId}`, label: '返回模型详情' },
))
const selectedFormat = computed(() => formats.value.find((item) => item.value === format.value))
const previewUrl = computed(() => current.value ? inferenceFileUrl(current.value.id, view.value === 'source' ? 'preview' : 'result') : '')
const isWorking = computed(() => ['queued', 'running'].includes(current.value?.status || ''))
const statusLabel = computed(() => {
  const labels: Record<string, string> = { queued: '等待 GPU', running: '推理中', succeeded: '已完成', failed: '失败', canceled: '已取消' }
  return labels[current.value?.status || ''] || '未开始'
})
const statusTone = computed<'ok' | 'danger' | 'warn' | 'idle'>(() => current.value?.status === 'succeeded' ? 'ok' : current.value?.status === 'failed' ? 'danger' : isWorking.value ? 'warn' : 'idle')

function downloadArtifact(command: string | number | object) {
  const artifact = artifacts.value.find((item) => item.id === command)
  if (artifact?.status === 'ready') window.location.assign(modelArtifactDownloadUrl(artifact.id))
}

watch(selectedFormat, (value) => {
  if (value?.fixed) parameters.value.image_size = value.fixed
})

async function load() {
  ;[model.value, artifacts.value, current.value, saved.value] = await Promise.all([
    getInferenceModel(modelId), listModelArtifacts(modelId), getCurrentInference(modelId), listSavedInference(modelId),
  ])
  if (current.value) parameters.value = { ...current.value.parameters }
  startPolling()
}

function chooseFile() { fileInput.value?.click() }
function selected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  const inputType = file.type.startsWith('video/') ? 'video' : 'image'
  const limit = inputType === 'video' ? 500 * 1024 * 1024 : 20 * 1024 * 1024
  if (file.size > limit) {
    ElMessage.error(`${inputType === 'video' ? '视频' : '图片'}不能超过 ${limit / 1024 / 1024} MB。`)
    ;(event.target as HTMLInputElement).value = ''
    return
  }
  pendingFile.value = file
}

async function run() {
  if (!pendingFile.value || busy.value) return
  const inputType = pendingFile.value.type.startsWith('video/') ? 'video' : 'image'
  let replace = false
  if (current.value) {
    await ElMessageBox.confirm('上传新文件将替换当前未保存的推理会话，已保存结果不受影响。', '替换当前会话', { confirmButtonText: '替换并运行', cancelButtonText: '取消', type: 'warning' })
    replace = true
  }
  busy.value = true
  try {
    current.value = await createInference(modelId, pendingFile.value, inputType, format.value, parameters.value, replace)
    view.value = current.value.status === 'succeeded' ? 'result' : 'source'
    pendingFile.value = undefined
    ElMessage.success(inputType === 'video' ? '视频已上传，后台推理已开始。' : '图片推理已完成。')
    startPolling()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '推理失败')
  } finally { busy.value = false }
}

async function clear() {
  if (!current.value) return
  await ElMessageBox.confirm('将清除上传文件和检测结果；已保存结果不受影响。', '清理当前会话', { confirmButtonText: '清理', cancelButtonText: '取消', type: 'warning' })
  await deleteInference(current.value.id)
  current.value = null
  stopPolling()
  ElMessage.success('当前推理会话已清理。')
}

async function save() {
  if (!current.value) return
  current.value = await saveInference(current.value.id)
  saved.value = await listSavedInference(modelId)
  current.value = null
  ElMessage.success('推理结果已保存。')
}

async function removeSaved(item: ModelInferenceRun) {
  try {
    await ElMessageBox.confirm('永久删除该推理源文件和检测结果？', '删除已保存结果', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  try {
    await deleteInference(item.id)
    saved.value = saved.value.filter((value) => value.id !== item.id)
    ElMessage.success('已保存推理结果已删除。')
  } catch (reason) { ElMessage.error(reason instanceof Error ? reason.message : '删除失败') }
}

function startPolling() {
  stopPolling()
  if (!isWorking.value || !current.value) return
  pollTimer = window.setInterval(async () => {
    if (!current.value) return
    current.value = await getInference(current.value.id)
    if (!isWorking.value) stopPolling()
  }, 1000)
}
function stopPolling() { if (pollTimer) window.clearInterval(pollTimer); pollTimer = undefined }
async function keepalive() { if (current.value && document.visibilityState === 'visible') current.value = await keepInferenceAlive(current.value.id) }
function visibilityChanged() { if (document.visibilityState === 'visible') void keepalive() }

onMounted(async () => {
  await load()
  keepaliveTimer = window.setInterval(keepalive, 5 * 60 * 1000)
  document.addEventListener('visibilitychange', visibilityChanged)
})
onBeforeUnmount(() => {
  stopPolling()
  if (keepaliveTimer) window.clearInterval(keepaliveTimer)
  document.removeEventListener('visibilitychange', visibilityChanged)
})
</script>

<template>
  <main class="content-page inference-page">
    <PageHeader :title="model ? `${model.name} · 在线推理` : '在线推理'" kind="model" :code="model?.model_code" :back-to="backTarget.to" :back-label="backTarget.label">
      <template #meta><span>图片最大 20 MB</span><span>视频最大 500 MB</span><span>会话 24 小时无访问后清理</span></template>
      <template #actions>
        <div v-if="model?.status === 'ready'" class="download-split">
          <VButton :href="modelDownloadUrl(model.id)" title="下载 PyTorch 模型"><template #icon><el-icon><Download /></el-icon></template>下载模型</VButton>
          <el-dropdown trigger="click" @command="downloadArtifact">
            <VButton icon-only label="选择转换格式" title="选择转换格式"><template #icon><el-icon><ArrowDown /></el-icon></template></VButton>
            <template #dropdown><el-dropdown-menu><el-dropdown-item v-for="artifact in artifacts" :key="artifact.id" :command="artifact.id" :disabled="artifact.status !== 'ready'">下载 {{ artifact.format === 'onnx' ? 'ONNX' : 'TensorRT' }}</el-dropdown-item><el-dropdown-item v-if="!artifacts.length" disabled>暂无转换产物</el-dropdown-item></el-dropdown-menu></template>
          </el-dropdown>
        </div>
        <VButton v-if="current?.status === 'succeeded' && model?.can_manage" variant="primary" @click="save">保存推理结果</VButton>
        <VButton v-if="current" variant="danger" @click="clear"><template #icon><el-icon><Delete /></el-icon></template>清理</VButton>
      </template>
    </PageHeader>

    <div class="content-body inference-layout">
      <section class="stage-column">
        <VPanel title="检测画布" flush>
          <template #actions>
            <el-segmented v-if="current?.status === 'succeeded'" v-model="view" :options="[{ label: '原始', value: 'source' }, { label: '检测结果', value: 'result' }]" />
            <VTag :tone="statusTone">{{ statusLabel }}</VTag>
          </template>
          <div class="inference-stage">
            <template v-if="current">
              <video v-if="current.input_type === 'video'" :src="previewUrl" controls preload="metadata" />
              <img v-else :src="previewUrl" alt="在线推理预览" />
              <div v-if="isWorking" class="stage-overlay"><span class="stage-spinner" /><strong>{{ current.status === 'queued' ? '等待可用 GPU' : '正在生成检测结果' }}</strong><small>关闭页面不会中断任务</small></div>
              <div v-if="current.status === 'failed'" class="stage-overlay is-error"><strong>推理失败</strong><small>{{ current.error }}</small></div>
            </template>
            <div v-else class="stage-empty"><UploadFilled /><strong>选择图片或视频开始推理</strong><span>上传后会保留当前会话，意外离开页面也可继续查看。</span></div>
          </div>
        </VPanel>

        <VPanel v-if="current?.status === 'succeeded'" title="检测结果">
          <div class="result-summary">
            <div><span>检测目标</span><strong>{{ current.statistics.detections ?? 0 }}</strong></div>
            <div v-if="current.input_type === 'video'"><span>处理帧数</span><strong>{{ current.statistics.processed_frames ?? '—' }}</strong></div>
            <div><span>推理耗时</span><strong>{{ Number(current.statistics.inference_seconds || 0).toFixed(2) }} s</strong></div>
            <div v-if="current.statistics.inference_fps"><span>推理 FPS</span><strong>{{ Number(current.statistics.inference_fps).toFixed(1) }}</strong></div>
          </div>
          <div class="result-actions">
            <VButton :href="inferenceFileUrl(current.id, 'source')"><template #icon><el-icon><Download /></el-icon></template>下载源文件</VButton>
            <VButton :href="inferenceFileUrl(current.id, 'result')"><template #icon><el-icon><Download /></el-icon></template>下载检测结果</VButton>
          </div>
        </VPanel>
      </section>

      <aside class="control-column">
        <VPanel title="推理设置">
          <div class="control-stack">
            <label>模型格式<el-select v-model="format" :disabled="isWorking" :title="isWorking ? '当前推理期间不可切换格式' : undefined"><el-option v-for="item in formats" :key="item.value" :value="item.value" :label="item.label" :disabled="!item.enabled" /></el-select></label>
            <label>置信度 <b>{{ parameters.confidence.toFixed(2) }}</b><el-slider v-model="parameters.confidence" :min="0" :max="1" :step="0.01" /></label>
            <label>IOU <b>{{ parameters.iou.toFixed(2) }}</b><el-slider v-model="parameters.iou" :min="0" :max="1" :step="0.01" /></label>
            <label>图像尺寸<el-input-number v-model="parameters.image_size" :min="32" :max="8192" :step="32" :disabled="selectedFormat?.fixed != null" :title="selectedFormat?.fixed != null ? '该转换产物使用固定输入尺寸' : undefined" /><small v-if="selectedFormat?.fixed">该转换产物固定为 {{ selectedFormat.fixed }}px</small></label>
            <input ref="fileInput" class="visually-hidden" type="file" accept="image/*,video/*" @change="selected" />
            <VButton class="upload-button" @click="chooseFile"><template #icon><el-icon><UploadFilled /></el-icon></template>{{ pendingFile?.name || '选择图片或视频' }}</VButton>
            <VButton variant="primary" :disabled="!pendingFile || isWorking" :loading="busy" :title="isWorking ? '当前推理完成后可再次开始' : !pendingFile ? '请先选择图片或视频' : '开始推理'" @click="run">开始推理</VButton>
          </div>
        </VPanel>
      </aside>

      <VPanel v-if="saved.length" class="saved-panel" title="已保存结果">
        <div class="saved-grid"><article v-for="item in saved" :key="item.id"><div><strong>{{ item.input_type === 'image' ? '图片推理' : '视频推理' }}</strong><span>{{ item.saved_at?.slice(0, 16).replace('T', ' ') }}</span></div><VTag tone="ok">{{ item.format.toUpperCase() }}</VTag><div class="saved-actions"><VButton size="sm" :href="inferenceFileUrl(item.id, 'result')">下载结果</VButton><VButton v-if="model?.can_manage" variant="danger" size="sm" @click="removeSaved(item)">删除</VButton></div></article></div>
      </VPanel>
    </div>
  </main>
</template>

<style scoped>
.inference-layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 18px; align-items: start; }
.stage-column { display: grid; gap: 18px; min-width: 0; }
.control-column { position: sticky; top: 16px; }
.inference-stage { position: relative; display: grid; place-items: center; min-height: 580px; overflow: hidden; background: #10181c; border-radius: 0 0 var(--vdw-radius-panel) var(--vdw-radius-panel); }
.inference-stage img, .inference-stage video { display: block; width: 100%; height: 580px; object-fit: contain; }
.stage-empty, .stage-overlay { display: grid; place-items: center; gap: 10px; color: #dbe4e7; text-align: center; }
.stage-empty svg { width: 42px; fill: #73868d; }
.stage-empty span, .stage-overlay small { color: #92a3a9; font-size: 14px; }
.stage-overlay { position: absolute; inset: 0; background: rgb(10 18 22 / 82%); }
.stage-overlay.is-error strong { color: #ffb5ab; }
.stage-spinner { width: 30px; height: 30px; border: 3px solid rgb(255 255 255 / 22%); border-top-color: #61c6d7; border-radius: 50%; animation: spin .8s linear infinite; }
.control-stack { display: grid; gap: 18px; }
.control-stack label { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; color: var(--vdw-ink-2); font-size: 14px; }
.control-stack label > :deep(.el-select), .control-stack label > :deep(.el-input-number), .control-stack label > :deep(.el-slider), .control-stack label > small { grid-column: 1 / -1; width: 100%; }
.control-stack small { color: var(--vdw-ink-3); line-height: 1.5; }
.download-split { display: inline-flex; }
.download-split > :first-child { border-radius: var(--vdw-radius-control) 0 0 var(--vdw-radius-control); }
.download-split :deep(.el-dropdown .vdw-btn) { width: var(--vdw-control-height); padding: 0; border-left: 0; border-radius: 0 var(--vdw-radius-control) var(--vdw-radius-control) 0; }
.upload-button { max-width: 100%; overflow: hidden; }
.result-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.result-summary div { padding: 14px; background: var(--vdw-surface-2); border: 1px solid var(--vdw-line); border-radius: var(--vdw-radius-control); }
.result-summary span, .result-summary strong { display: block; }
.result-summary span { color: var(--vdw-ink-3); font-size: 13px; }
.result-summary strong { margin-top: 6px; font: 600 20px/1 var(--vdw-mono); }
.result-actions { display: flex; gap: 10px; margin-top: 16px; }
.saved-panel { grid-column: 1 / -1; }
.saved-grid { display: grid; gap: 8px; }
.saved-grid article { display: grid; grid-template-columns: 1fr auto auto; gap: 12px; align-items: center; padding: 10px 12px; border: 1px solid var(--vdw-line); border-radius: var(--vdw-radius-control); }
.saved-actions { display: flex; gap: 6px; }
.saved-grid article span { display: block; margin-top: 3px; color: var(--vdw-ink-3); font-size: 13px; }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .stage-spinner { animation: none; } }
</style>
