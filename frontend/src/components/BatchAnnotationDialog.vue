<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'

import {
  createProjectBatchAutoAnnotation,
  listModelProjectModels,
  listModelProjects,
  listXAnyLabelingModels,
  type AutoAnnotationConfig,
  type InferenceModel,
  type ModelProject,
  type RemoteModelOption,
} from '../api/models'
import type { Video } from '../api/media'
import VButton from '../ui/VButton.vue'

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

const source = ref<'local' | 'xanylabeling'>('local')
const modelProjects = ref<ModelProject[]>([])
const models = ref<InferenceModel[]>([])
const remoteModels = ref<RemoteModelOption[]>([])
const projectId = ref('')
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

function modelOptionId(item: InferenceModel | RemoteModelOption) {
  return 'id' in item ? item.id : item.model_id
}

async function loadModels() {
  error.value = ''
  try {
    if (source.value === 'xanylabeling') {
      remoteModels.value = await listXAnyLabelingModels()
      modelId.value = remoteModels.value[0]?.model_id || ''
      return
    }
    modelProjects.value = await listModelProjects()
    if (!projectId.value || !modelProjects.value.some((item) => item.id === projectId.value)) {
      projectId.value = modelProjects.value[0]?.id || ''
    }
    models.value = projectId.value ? await listModelProjectModels(projectId.value) : []
    modelId.value = models.value[0]?.id || ''
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '模型列表加载失败'
  }
}

watch(() => props.modelValue, (open) => {
  if (open) {
    riskConfirmed.value = false
    overwrite.value = false
    void loadModels()
  }
}, { immediate: true })
watch(source, () => void loadModels())
watch(projectId, async (value) => {
  if (source.value !== 'local' || !value) return
  models.value = await listModelProjectModels(value)
  modelId.value = models.value[0]?.id || ''
})

async function submit() {
  if (!valid.value) return
  loading.value = true
  error.value = ''
  const config: AutoAnnotationConfig = {
    source: source.value,
    model_id: modelId.value,
    remote_task_id: source.value === 'xanylabeling'
      ? remoteModels.value.find((item) => item.model_id === modelId.value)?.task_id || null
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
        <el-form-item label="标注模型来源">
          <el-radio-group v-model="source" :disabled="settingsDisabled">
            <el-radio value="local">模型项目</el-radio>
            <el-radio value="xanylabeling">X-anylabeling-server</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="source === 'local'" label="模型项目">
          <el-select v-model="projectId" :disabled="settingsDisabled" placeholder="选择模型项目" style="width: 100%">
            <el-option v-for="item in modelProjects" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型">
          <el-select v-model="modelId" :disabled="settingsDisabled" placeholder="选择模型" style="width: 100%">
            <el-option
              v-for="item in (source === 'local' ? models : remoteModels)"
              :key="modelOptionId(item)"
              :label="item.name"
              :value="modelOptionId(item)"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="类别（可选，逗号分隔）">
          <el-input v-model="categories" :disabled="settingsDisabled" placeholder="例如：person, car" />
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
</template>

<style scoped>
.annotation-number-row { display: flex; gap: 16px; }
.annotation-number-row .el-form-item { flex: 1; }
.batch-annotation-form { display: grid; gap: 14px; }
.batch-annotation-form > p { margin: 0; color: var(--el-text-color-regular); }
.risk-confirmation { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 14px; color: var(--el-color-danger); background: var(--el-color-danger-light-9); border: 1px solid var(--el-color-danger-light-5); border-radius: 4px; }
.form-error { color: var(--el-color-danger); }
</style>
