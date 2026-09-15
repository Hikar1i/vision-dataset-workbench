<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'

import {
  createProjectBatchAutoAnnotation,
  getXAnyLabelingSetting,
  listModelProjectModels,
  listModelProjects,
  listXAnyLabelingModels,
  type AutoAnnotationConfig,
  type InferenceModel,
  type ModelProject,
  type RemoteModelOption,
  type XAnyLabelingSetting,
} from '../api/models'
import { listLLMConfigs, type LLMConfig } from '../api/llm'
import type { Video } from '../api/media'
import VButton from '../ui/VButton.vue'
import XAnyLabelingSettingsDialog from './XAnyLabelingSettingsDialog.vue'

type ModelSourceValue = 'xanylabeling' | 'online' | `project:${string}`

const props = defineProps<{
  modelValue: boolean
  projectId: string
  videos: Video[]
  scope: 'unannotated' | 'all'
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submitted: [accepted: string[]]
}>()

const source = ref<ModelSourceValue>('' as ModelSourceValue)
const modelProjects = ref<ModelProject[]>([])
const models = ref<InferenceModel[]>([])
const remoteModels = ref<RemoteModelOption[]>([])
const llmConfigs = ref<LLMConfig[]>([])
const xanylabelingSetting = ref<XAnyLabelingSetting | null>(null)
const xanylabelingSettingsOpen = ref(false)
const modelId = ref('')
const categories = ref('')
const confidence = ref(0.25)
const iou = ref(0.45)
const overwrite = ref(false)
const riskConfirmed = ref(false)
const loading = ref(false)
const error = ref('')

const annotatedCount = computed(() => props.videos.filter((video) => video.has_annotations).length)
const unannotatedCount = computed(() => props.videos.length - annotatedCount.value)
const valid = computed(() => Boolean(modelId.value) && props.videos.length > 0)
const settingsDisabled = computed(() => props.scope === 'all' && !riskConfirmed.value)

const selectedProjectId = computed(() => source.value.startsWith('project:')
  ? source.value.slice('project:'.length)
  : '')
const selectedRemoteModel = computed(() =>
  remoteModels.value.find((item) => item.key === modelId.value) ?? null,
)
const modelOptions = computed(() => source.value === 'xanylabeling'
  ? remoteModels.value.map((item) => ({ id: item.key, name: item.name }))
  : source.value === 'online'
    ? llmConfigs.value.map((item) => ({ id: item.id, name: item.name }))
    : models.value.map((item) => ({ id: item.id, name: item.name })))

async function loadModels() {
  error.value = ''
  try {
    if (source.value === 'xanylabeling') {
      remoteModels.value = await listXAnyLabelingModels()
      modelId.value = remoteModels.value[0]?.key || ''
      return
    }
    if (source.value === 'online') {
      llmConfigs.value = (await listLLMConfigs()).filter((item) => item.enabled)
      modelId.value = llmConfigs.value.find((item) => item.available)?.id || ''
      return
    }
    models.value = selectedProjectId.value
      ? (await listModelProjectModels(selectedProjectId.value)).filter((item) => item.status === 'ready')
      : []
    modelId.value = models.value[0]?.id || ''
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '模型列表加载失败'
  }
}

async function loadSources() {
  error.value = ''
  try {
    const [projects, setting] = await Promise.all([
      listModelProjects(),
      getXAnyLabelingSetting(),
    ])
    modelProjects.value = projects
    xanylabelingSetting.value = setting
    const selectedExists = source.value === 'xanylabeling'
      || source.value === 'online'
      || projects.some((item) => `project:${item.id}` === source.value)
    if (!selectedExists) source.value = projects[0] ? `project:${projects[0].id}` : 'online'
    await loadModels()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '模型来源加载失败'
  }
}

async function changeSource(value: ModelSourceValue) {
  source.value = value
  modelId.value = ''
  if (value === 'xanylabeling') {
    xanylabelingSettingsOpen.value = true
    return
  }
  await loadModels()
}

function savedXAnyLabeling(setting: XAnyLabelingSetting, items: RemoteModelOption[]) {
  xanylabelingSetting.value = setting
  remoteModels.value = items
  source.value = 'xanylabeling'
  modelId.value = items[0]?.key || ''
}

watch(() => props.modelValue, (open) => {
  if (open) {
    riskConfirmed.value = false
    overwrite.value = false
    void loadSources()
  }
}, { immediate: true })

async function submit() {
  if (!valid.value) return
  loading.value = true
  error.value = ''
  const config: AutoAnnotationConfig = {
    source: source.value === 'xanylabeling'
      ? 'xanylabeling'
      : source.value === 'online' ? 'online' : 'local',
    model_id: selectedRemoteModel.value?.model_id ?? modelId.value,
    remote_task_id: source.value === 'xanylabeling'
      ? selectedRemoteModel.value?.task_id || null
      : null,
    categories: categories.value.split(',').map((item) => item.trim()).filter(Boolean),
    confidence: confidence.value,
    iou: iou.value,
  }
  try {
    const result = await createProjectBatchAutoAnnotation(
      props.projectId,
      props.videos.map((video) => video.id),
      config,
      props.scope,
      props.scope === 'all' ? overwrite.value : false,
    )
    if (result.rejected.length) ElMessage.warning(`已创建任务，拒绝 ${result.rejected.length} 个视频。`)
    else ElMessage.success(`已创建 ${result.accepted_video_ids.length} 个视频的自动标注任务。`)
    emit('submitted', result.accepted_video_ids)
    emit('update:modelValue', false)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '批量自动标注任务创建失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="批量自动标注"
    width="min(620px, calc(100vw - 32px))"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="batch-annotation-form">
      <el-alert
        v-if="scope === 'all'"
        title="将处理包含已有标注的视频"
        :description="`本次将处理全部 ${videos.length} 个视频，其中 ${annotatedCount} 个已有标注。`"
        type="error"
        show-icon
        :closable="false"
      />
      <p v-else>将处理 {{ unannotatedCount }} 个未标注视频。</p>
      <div v-if="scope === 'all'" class="risk-confirmation">
        <span>确认要对已标注的视频执行自动标注操作</span>
        <el-switch v-model="riskConfirmed" data-test="annotation-risk-confirm" />
      </div>
      <el-form label-position="top">
        <el-form-item label="模型项目">
          <el-select
            :model-value="source"
            data-test="model-project-select"
            :disabled="settingsDisabled"
            placeholder="选择模型项目"
            style="width: 100%"
            @change="changeSource"
          >
            <el-option
              data-test="model-source-option"
              value="xanylabeling"
              :label="`X-anylabeling-server（${xanylabelingSetting?.available ? '可用' : '不可用'}）`"
            />
            <el-option data-test="model-source-option" value="online" label="在线大模型" />
            <el-option
              v-for="item in modelProjects"
              :key="item.id"
              data-test="model-source-option"
              :label="item.name"
              :value="`project:${item.id}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="模型">
          <el-select v-model="modelId" data-test="inference-model-select" :disabled="settingsDisabled" placeholder="选择模型" style="width: 100%">
            <el-option
              v-for="item in modelOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="类别（可选，逗号分隔）">
          <el-input v-model="categories" data-test="annotation-categories" :disabled="settingsDisabled" placeholder="例如：person, car" />
        </el-form-item>
        <div class="annotation-number-row">
          <el-form-item label="置信度"><el-input-number v-model="confidence" :disabled="settingsDisabled" :min="0" :max="1" :step="0.05" /></el-form-item>
          <el-form-item label="IoU"><el-input-number v-model="iou" :disabled="settingsDisabled" :min="0" :max="1" :step="0.05" /></el-form-item>
        </div>
        <el-checkbox v-model="overwrite" data-test="annotation-overwrite" :disabled="scope === 'unannotated' || settingsDisabled">覆盖已有模型标注</el-checkbox>
      </el-form>
      <p v-if="error" class="form-error">{{ error }}</p>
    </div>
    <template #footer>
      <VButton variant="default" @click="emit('update:modelValue', false)">取消</VButton>
      <VButton variant="primary" data-test="annotation-create-task" :loading="loading" :disabled="!valid || settingsDisabled" @click="submit">创建任务</VButton>
    </template>
  </el-dialog>
  <XAnyLabelingSettingsDialog
    v-model="xanylabelingSettingsOpen"
    :setting="xanylabelingSetting"
    @saved="savedXAnyLabeling"
  />
</template>

<style scoped>
.annotation-number-row { display: flex; gap: 16px; }
.annotation-number-row .el-form-item { flex: 1; }
.batch-annotation-form { display: grid; gap: 14px; }
.batch-annotation-form > p { margin: 0; color: var(--el-text-color-regular); }
.risk-confirmation { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 14px; color: var(--el-color-danger); background: var(--el-color-danger-light-9); border: 1px solid var(--el-color-danger-light-5); border-radius: 4px; }
.form-error { color: var(--el-color-danger); }
</style>
