<script setup lang="ts">
import { ElMessageBox } from 'element-plus'
import { notify } from '../ui/notify'
import { ArrowDown, Delete, Download, UploadFilled } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { can } from '../api/access'

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
import VEmpty from '../ui/VEmpty.vue'
import VPanel from '../ui/VPanel.vue'
import VTag from '../ui/VTag.vue'

const route = useRoute()
const modelId = String(route.params.modelId)
const model = ref<InferenceModel>()
const artifacts = ref<ModelArtifact[]>([])
const current = ref<ModelInferenceRun | null>(null)
const saved = ref<ModelInferenceRun[]>([])
const mode = ref<'current' | 'saved'>('current')
const selectedSaved = ref<ModelInferenceRun>()
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
const displayedRun = computed(() => mode.value === 'saved' ? selectedSaved.value : current.value || undefined)
const previewUrl = computed(() => displayedRun.value ? inferenceFileUrl(displayedRun.value.id, view.value === 'source' ? 'preview' : 'result') : '')
const isWorking = computed(() => ['queued', 'running'].includes(current.value?.status || ''))
const displayedWorking = computed(() => ['queued', 'running'].includes(displayedRun.value?.status || ''))
const canExecute = computed(() => can(model.value?.access, 'task.execute'))
const canUpdate = computed(() => can(model.value?.access, 'project.update'))
const statusLabel = computed(() => {
  const labels: Record<string, string> = { queued: '等待 GPU', running: '推理中', succeeded: '已完成', failed: '失败', canceled: '已取消' }
  return labels[displayedRun.value?.status || ''] || '未开始'
})
const statusTone = computed<'ok' | 'danger' | 'warn' | 'idle'>(() => displayedRun.value?.status === 'succeeded' ? 'ok' : displayedRun.value?.status === 'failed' ? 'danger' : displayedWorking.value ? 'warn' : 'idle')

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
  if (mode.value === 'saved') {
    selectedSaved.value = saved.value.find((item) => item.id === selectedSaved.value?.id) ?? saved.value[0]
  }
  startPolling()
}

function showCurrent() {
  mode.value = 'current'
  view.value = current.value?.status === 'succeeded' ? 'result' : 'source'
}

function openSaved(item?: ModelInferenceRun) {
  mode.value = 'saved'
  selectedSaved.value = item ?? saved.value[0]
  view.value = 'result'
}

function chooseFile() { fileInput.value?.click() }
function selected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  const inputType = file.type.startsWith('video/') ? 'video' : 'image'
  const limit = inputType === 'video' ? 500 * 1024 * 1024 : 20 * 1024 * 1024
  if (file.size > limit) {
    notify.error(`${inputType === 'video' ? '视频' : '图片'}不能超过 ${limit / 1024 / 1024} MB。`)
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
    notify.success(inputType === 'video' ? '视频已上传，后台推理已开始。' : '图片推理已完成。')
    startPolling()
  } catch (reason) {
    notify.error(reason instanceof Error ? reason.message : '推理失败')
  } finally { busy.value = false }
}

async function clear() {
  if (!current.value) return
  await ElMessageBox.confirm('将清除上传文件和检测结果；已保存结果不受影响。', '清理当前会话', { confirmButtonText: '清理', cancelButtonText: '取消', type: 'warning' })
  await deleteInference(current.value.id)
  current.value = null
  stopPolling()
  notify.success('当前推理会话已清理。')
}

async function save() {
  if (!current.value) return
  const savedRun = await saveInference(current.value.id)
  saved.value = await listSavedInference(modelId)
  current.value = null
  stopPolling()
  openSaved(saved.value.find((item) => item.id === savedRun.id) ?? savedRun)
  notify.success('推理结果已保存，可在“已保存结果”中查看。')
}

async function removeSaved(item: ModelInferenceRun) {
  try {
    await ElMessageBox.confirm('永久删除该推理源文件和检测结果？', '删除已保存结果', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  try {
    await deleteInference(item.id)
    saved.value = saved.value.filter((value) => value.id !== item.id)
    if (selectedSaved.value?.id === item.id) selectedSaved.value = saved.value[0]
    notify.success('已保存推理结果已删除。')
  } catch (reason) { notify.error(reason instanceof Error ? reason.message : '删除失败') }
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
        <div v-if="model?.status === 'ready' && can(model.access, 'artifact.download')" class="download-split">
          <VButton :href="modelDownloadUrl(model.id)" title="下载 PyTorch 模型"><template #icon><el-icon><Download /></el-icon></template>下载模型</VButton>
          <el-dropdown trigger="click" @command="downloadArtifact">
            <VButton icon-only label="选择转换格式" title="选择转换格式"><template #icon><el-icon><ArrowDown /></el-icon></template></VButton>
            <template #dropdown><el-dropdown-menu><el-dropdown-item v-for="artifact in artifacts" :key="artifact.id" :command="artifact.id" :disabled="artifact.status !== 'ready'">下载 {{ artifact.format === 'onnx' ? 'ONNX' : 'TensorRT' }}</el-dropdown-item><el-dropdown-item v-if="!artifacts.length" disabled>暂无转换产物</el-dropdown-item></el-dropdown-menu></template>
          </el-dropdown>
        </div>
        <VButton v-if="mode === 'current' && current?.status === 'succeeded' && canUpdate" data-test="save-inference" variant="primary" @click="save">保存推理结果</VButton>
        <VButton v-if="mode === 'current' && current && canExecute" variant="danger" @click="clear"><template #icon><el-icon><Delete /></el-icon></template>清理</VButton>
      </template>
    </PageHeader>

    <div class="content-body inference-body">
      <div class="inference-modes" role="tablist" aria-label="推理结果视图">
        <button data-test="inference-mode-current" :class="{ active: mode === 'current' }" role="tab" :aria-selected="mode === 'current'" @click="showCurrent">当前推理</button>
        <button data-test="inference-mode-saved" :class="{ active: mode === 'saved' }" role="tab" :aria-selected="mode === 'saved'" @click="openSaved()">已保存结果 <span>{{ saved.length }}</span></button>
      </div>

      <div class="inference-layout">
        <section class="stage-column">
        <VPanel title="检测画布" flush>
          <template #actions>
            <el-segmented v-if="displayedRun?.status === 'succeeded'" v-model="view" :options="[{ label: '原始', value: 'source' }, { label: '检测结果', value: 'result' }]" />
            <VTag :tone="statusTone">{{ statusLabel }}</VTag>
          </template>
          <div class="inference-stage">
            <template v-if="displayedRun">
              <video v-if="displayedRun.input_type === 'video'" :src="previewUrl" controls preload="metadata" />
              <img v-else :src="previewUrl" alt="在线推理预览" />
              <div v-if="displayedWorking" class="stage-overlay"><span class="stage-spinner" /><strong>{{ displayedRun.status === 'queued' ? '等待可用 GPU' : '正在生成检测结果' }}</strong><small>关闭页面不会中断任务</small></div>
              <div v-if="displayedRun.status === 'failed'" class="stage-overlay is-error"><strong>推理失败</strong><small>{{ displayedRun.error }}</small></div>
            </template>
            <div v-else class="stage-empty"><UploadFilled /><strong>{{ mode === 'saved' ? '还没有已保存结果' : '选择图片或视频开始推理' }}</strong><span>{{ mode === 'saved' ? '完成推理并保存后，可在这里再次查看。' : '上传后会保留当前会话，意外离开页面也可继续查看。' }}</span></div>
          </div>
        </VPanel>

        <VPanel v-if="displayedRun?.status === 'succeeded'" title="检测结果">
          <div class="result-summary">
            <div><span>检测目标</span><strong>{{ displayedRun.statistics.detections ?? 0 }}</strong></div>
            <div v-if="displayedRun.input_type === 'video'"><span>处理帧数</span><strong>{{ displayedRun.statistics.processed_frames ?? '—' }}</strong></div>
            <div><span>推理耗时</span><strong>{{ Number(displayedRun.statistics.inference_seconds || 0).toFixed(2) }} s</strong></div>
            <div v-if="displayedRun.statistics.inference_fps"><span>推理 FPS</span><strong>{{ Number(displayedRun.statistics.inference_fps).toFixed(1) }}</strong></div>
          </div>
          <div class="result-actions">
            <VButton :href="inferenceFileUrl(displayedRun.id, 'source')"><template #icon><el-icon><Download /></el-icon></template>下载源文件</VButton>
            <VButton :href="inferenceFileUrl(displayedRun.id, 'result')"><template #icon><el-icon><Download /></el-icon></template>下载检测结果</VButton>
          </div>
        </VPanel>
        </section>

        <aside class="control-column">
          <VPanel v-if="mode === 'current' && canExecute" title="推理设置">
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
          <VPanel v-else title="已保存结果">
            <div v-if="saved.length" class="saved-list">
              <article v-for="item in saved" :key="item.id" :class="{ active: selectedSaved?.id === item.id }" :data-test="`saved-inference-run-${item.id}`">
                <button class="saved-item__select" type="button" @click="openSaved(item)">
                  <span><strong>{{ item.input_type === 'image' ? '图片推理' : '视频推理' }}</strong><small>{{ item.saved_at?.slice(0, 16).replace('T', ' ') }}</small></span>
                  <VTag tone="ok">{{ item.format.toUpperCase() }}</VTag>
                </button>
                <div class="saved-actions">
                  <VButton size="sm" :href="inferenceFileUrl(item.id, 'result')"><template #icon><el-icon><Download /></el-icon></template>下载结果</VButton>
                  <VButton v-if="canUpdate" variant="danger" size="sm" @click="removeSaved(item)"><template #icon><el-icon><Delete /></el-icon></template>删除</VButton>
                </div>
              </article>
            </div>
            <VEmpty v-else title="还没有已保存结果" note="完成当前推理并保存后，可在这里长期查看。">
              <VButton @click="showCurrent">返回当前推理</VButton>
            </VEmpty>
          </VPanel>
        </aside>
      </div>
    </div>
  </main>
</template>

<style scoped>
.inference-body { display: grid; gap: 14px; align-content: start; }
.inference-modes { display: flex; gap: 4px; width: fit-content; padding: 4px; background: var(--vdw-surface-2); border: 1px solid var(--vdw-line); border-radius: var(--vdw-radius-control); }
.inference-modes button { height: 32px; padding: 0 14px; border: 0; border-radius: calc(var(--vdw-radius-control) - 2px); color: var(--vdw-ink-2); background: transparent; cursor: pointer; font: 500 14px/1 var(--vdw-sans); }
.inference-modes button:hover { color: var(--vdw-ink); background: var(--vdw-surface-3); }
.inference-modes button.active { color: var(--vdw-ink); background: var(--vdw-surface); box-shadow: var(--vdw-shadow-1); }
.inference-modes button span { margin-left: 5px; color: var(--vdw-ink-3); font: 600 13px var(--vdw-mono); }
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
.saved-list { display: grid; gap: 8px; max-height: 640px; overflow: auto; }
.saved-list article { display: grid; gap: 8px; padding: 9px; border: 1px solid var(--vdw-line); border-radius: var(--vdw-radius-control); transition: border-color var(--vdw-motion-fast) var(--vdw-ease), box-shadow var(--vdw-motion-fast) var(--vdw-ease); }
.saved-list article.active { border-color: var(--vdw-accent); box-shadow: inset 3px 0 var(--vdw-accent); }
.saved-item__select { display: flex; align-items: center; justify-content: space-between; gap: 10px; width: 100%; padding: 3px 4px; border: 0; color: inherit; background: transparent; text-align: left; cursor: pointer; }
.saved-item__select:hover strong { color: var(--vdw-accent-ink); }
.saved-item__select span { min-width: 0; }
.saved-item__select strong, .saved-item__select small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.saved-item__select small { margin-top: 3px; color: var(--vdw-ink-3); font-size: 13px; }
.saved-actions { display: flex; gap: 6px; }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .stage-spinner { animation: none; } }
</style>
