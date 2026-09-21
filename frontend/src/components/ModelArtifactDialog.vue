<script setup lang="ts">
import { Delete, Download, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { getCapabilities, type SystemCapabilities } from '../api/capabilities'
import {
  createModelArtifact,
  deleteModelArtifact,
  listModelArtifacts,
  modelArtifactDownloadUrl,
  type ModelArtifact,
} from '../api/modelArtifacts'
import VButton from '../ui/VButton.vue'
import VTag from '../ui/VTag.vue'
import { modelArtifactStatus } from '../ui/status'

const props = defineProps<{
  modelValue: boolean
  modelId: string
  modelName: string
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  changed: []
}>()

const artifacts = ref<ModelArtifact[]>([])
const capabilities = ref<SystemCapabilities>()
const loading = ref(false)
const submitting = ref<'onnx' | 'engine' | ''>('')
const onnxImageSize = ref(640)
const onnxDynamic = ref(false)
const engineImageSize = ref(640)
const enginePrecision = ref<'fp16' | 'fp32'>('fp16')

const byFormat = computed(() => new Map(artifacts.value.map((item) => [item.format, item])))
const onnx = computed(() => byFormat.value.get('onnx'))
const engine = computed(() => byFormat.value.get('engine'))

async function load() {
  if (!props.modelId) return
  loading.value = true
  try {
    ;[artifacts.value, capabilities.value] = await Promise.all([
      listModelArtifacts(props.modelId),
      getCapabilities(),
    ])
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '转换产物加载失败')
  } finally {
    loading.value = false
  }
}

async function create(format: 'onnx' | 'engine') {
  submitting.value = format
  try {
    const result = await createModelArtifact(props.modelId, {
      format,
      image_size: format === 'onnx' ? onnxImageSize.value : engineImageSize.value,
      dynamic: format === 'onnx' ? onnxDynamic.value : false,
      precision: enginePrecision.value,
    })
    artifacts.value = [...artifacts.value.filter((item) => item.format !== format), result.artifact]
    emit('changed')
    ElMessage.success(`${format === 'onnx' ? 'ONNX' : 'TensorRT'} 转换任务已创建。`)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '转换任务创建失败')
  } finally {
    submitting.value = ''
  }
}

async function remove(artifact: ModelArtifact) {
  try {
    await ElMessageBox.confirm(
      `删除 ${artifact.format === 'onnx' ? 'ONNX' : 'TensorRT'} 转换产物？`,
      '删除转换产物',
      { type: 'warning', confirmButtonText: '删除产物', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await deleteModelArtifact(artifact.id)
    artifacts.value = artifacts.value.filter((item) => item.id !== artifact.id)
    emit('changed')
    ElMessage.success('转换产物已删除。')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '转换产物删除失败')
  }
}

watch(() => props.modelValue, (open) => { if (open) void load() }, { immediate: true })
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="模型格式转换"
    width="860px"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="artifact-dialog">
      <p class="artifact-dialog__intro">
        基于“{{ modelName }}”生成可复用转换产物。每种格式仅保留一份，删除后才能重新构建。
      </p>

      <div class="artifact-grid">
        <section class="artifact-card">
          <header>
            <div><span class="artifact-card__mark">ONNX</span><h3>跨运行时交换格式</h3></div>
            <VTag v-if="onnx" :tone="modelArtifactStatus(onnx.status).tone">
              {{ modelArtifactStatus(onnx.status).label }}
            </VTag>
          </header>
          <p>适合跨平台部署和 ONNX Runtime CUDA 推理；不内嵌 NMS。</p>
          <div class="artifact-controls">
            <label>输入尺寸
              <el-input-number v-model="onnxImageSize" :min="32" :max="8192" :step="32" />
            </label>
            <label class="switch-control">动态输入
              <el-switch v-model="onnxDynamic" />
            </label>
          </div>
          <p v-if="onnx?.error" class="artifact-error">{{ onnx.error }}</p>
          <footer>
            <VButton
              v-if="!onnx"
              data-test="create-onnx-artifact"
              :loading="submitting === 'onnx'"
              :disabled="capabilities?.features.onnx_export.available !== true"
              :title="capabilities?.features.onnx_export.reason || '创建 ONNX 转换任务'"
              @click="create('onnx')"
            ><template #icon><el-icon><RefreshRight /></el-icon></template>转换为 ONNX</VButton>
            <template v-else>
              <VButton
                size="sm"
                :href="onnx.status === 'ready' ? modelArtifactDownloadUrl(onnx.id) : undefined"
                :disabled="onnx.status !== 'ready'"
              ><template #icon><el-icon><Download /></el-icon></template>下载</VButton>
              <VButton variant="danger" size="sm" @click="remove(onnx)">
                <template #icon><el-icon><Delete /></el-icon></template>删除
              </VButton>
            </template>
          </footer>
        </section>

        <section class="artifact-card artifact-card--engine">
          <header>
            <div><span class="artifact-card__mark">TRT</span><h3>本机 TensorRT 引擎</h3></div>
            <VTag v-if="engine" :tone="modelArtifactStatus(engine.status).tone">
              {{ modelArtifactStatus(engine.status).label }}
            </VTag>
          </header>
          <div class="engine-warning" role="note">
            仅保证在本机兼容环境使用；GPU、CUDA 或 TensorRT 变化后将自动失效。
          </div>
          <div class="artifact-controls">
            <label>输入尺寸
              <el-input-number v-model="engineImageSize" :min="32" :max="8192" :step="32" />
            </label>
            <label>精度
              <el-radio-group v-model="enginePrecision">
                <el-radio-button value="fp16">FP16</el-radio-button>
                <el-radio-button value="fp32">FP32</el-radio-button>
              </el-radio-group>
            </label>
          </div>
          <p v-if="engine?.error" class="artifact-error">{{ engine.error }}</p>
          <footer>
            <VButton
              v-if="!engine"
              data-test="create-engine-artifact"
              :loading="submitting === 'engine'"
              :disabled="capabilities?.features.tensorrt.available !== true"
              :title="capabilities?.features.tensorrt.reason || '创建 TensorRT 转换任务'"
              @click="create('engine')"
            ><template #icon><el-icon><RefreshRight /></el-icon></template>构建 TensorRT</VButton>
            <template v-else>
              <VButton
                size="sm"
                :href="engine.status === 'ready' ? modelArtifactDownloadUrl(engine.id) : undefined"
                :disabled="engine.status !== 'ready'"
              ><template #icon><el-icon><Download /></el-icon></template>下载</VButton>
              <VButton variant="danger" size="sm" @click="remove(engine)">
                <template #icon><el-icon><Delete /></el-icon></template>删除
              </VButton>
            </template>
          </footer>
        </section>
      </div>
    </div>
    <template #footer><VButton variant="default" @click="emit('update:modelValue', false)">关闭</VButton></template>
  </el-dialog>
</template>

<style scoped>
.artifact-dialog { display: grid; gap: 16px; }
.artifact-dialog__intro { margin: 0; color: var(--vdw-ink-2); font-size: 14px; }
.artifact-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.artifact-card { display: grid; align-content: start; gap: 14px; min-height: 330px; padding: 18px; border: 1px solid var(--vdw-line); border-radius: var(--vdw-radius-card); }
.artifact-card > header { display: flex; align-items: start; justify-content: space-between; gap: 12px; }
.artifact-card h3 { margin: 7px 0 0; font: 600 17px/1.25 var(--vdw-title); }
.artifact-card__mark { color: var(--vdw-accent-ink); font: 600 13px/1 var(--vdw-mono); letter-spacing: .08em; }
.artifact-card > p { margin: 0; color: var(--vdw-ink-2); font-size: 14px; line-height: 1.55; }
.artifact-controls { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; }
.artifact-controls label { display: grid; align-content: start; gap: 7px; color: var(--vdw-ink-2); font-size: 14px; }
.artifact-controls :deep(.el-input-number), .artifact-controls :deep(.el-radio-group) { width: 100%; }
.switch-control { grid-template-columns: 1fr auto; align-items: center; }
.engine-warning { padding: 10px 12px; color: var(--vdw-warn); font-size: 14px; line-height: 1.45; background: var(--vdw-warn-soft); border: 1px solid var(--vdw-warn-line); border-left-width: 3px; border-radius: var(--vdw-radius-control); }
.artifact-error { color: var(--vdw-danger) !important; overflow-wrap: anywhere; }
.artifact-card > footer { display: flex; align-items: center; gap: 6px; margin-top: auto; }
</style>
