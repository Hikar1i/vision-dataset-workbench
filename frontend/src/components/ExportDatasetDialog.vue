<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'

import {
  createDatasetExport,
  type DatasetExport,
  type DatasetExportLabel,
} from '../api/datasetExports'
import { listLabels } from '../api/labels'
import { listVideos } from '../api/media'
import VButton from '../ui/VButton.vue'

const props = defineProps<{ modelValue: boolean; projectId: string }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submitted: [value: DatasetExport]
}>()
const name = ref('')
const trainRatio = ref(0.8)
const mode = ref<'project' | 'manual'>('project')
const labels = ref<DatasetExportLabel[]>([])
const estimatedVideos = ref(0)
const estimatedFrames = ref(0)
const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const validationRatio = computed(() => (1 - trainRatio.value).toFixed(2))

const validationMessage = computed(() => {
  if (!labels.value.length) return '项目还没有标签，请先在标签管理页创建标签。'
  if (!labels.value.some((label) => label.enabled)) return '至少启用一个类别后才能导出。'
  return ''
})
const canSubmit = computed(() => (
  name.value.trim().length > 0
  && !validationMessage.value
  && !loading.value
  && !submitting.value
))

function move(index: number, offset: -1 | 1) {
  const target = index + offset
  if (target < 0 || target >= labels.value.length) return
  const reordered = [...labels.value]
  ;[reordered[index], reordered[target]] = [reordered[target], reordered[index]]
  labels.value = reordered.map((label, mapping) => ({ ...label, mapping }))
}

async function load() {
  loading.value = true
  error.value = ''
  name.value = ''
  trainRatio.value = 0.8
  mode.value = 'project'
  try {
    const [projectLabels, videos] = await Promise.all([
      listLabels(props.projectId),
      listVideos(props.projectId, 1, 999),
    ])
    labels.value = projectLabels.map((label, mapping) => ({
      source_label_id: label.id,
      name: label.name,
      mapping,
      enabled: label.enabled,
    }))
    const included = videos.items.filter((video) => (
      video.status === 'ready'
      && video.enabled
      && (video.sampling?.extracted_frames ?? 0) > 0
    ))
    estimatedVideos.value = included.length
    estimatedFrames.value = included.reduce(
      (total, video) => total + (video.sampling?.enabled_frames ?? 0),
      0,
    )
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '导出配置加载失败'
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!canSubmit.value) return
  submitting.value = true
  error.value = ''
  try {
    const created = await createDatasetExport(props.projectId, {
      name: name.value.trim(),
      train_ratio: trainRatio.value,
      labels: labels.value.map((label, mapping) => ({ ...label, mapping })),
    })
    ElMessage.success('数据集导出任务已创建。')
    emit('submitted', created)
    emit('update:modelValue', false)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '数据集导出任务创建失败'
  } finally {
    submitting.value = false
  }
}

watch(() => props.modelValue, (open) => {
  if (open) void load()
}, { immediate: true })
</script>

<template>
  <el-dialog
    append-to-body
    :model-value="modelValue"
    title="导出数据集"
    width="min(760px, calc(100vw - 32px))"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="export-form">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />

      <label class="field-row">
        <span>数据集名称</span>
        <el-input
          v-model="name"
          data-test="dataset-name"
          maxlength="128"
          placeholder="例如：火灾烟雾-v1"
        />
      </label>

      <div class="field-row ratio-row">
        <span>训练集 / 验证集比例</span>
        <el-slider v-model="trainRatio" :min="0" :max="1" :step="0.01" />
        <div class="ratio-inputs" data-test="ratio-inputs">
          <el-input-number
            v-model="trainRatio"
            data-test="train-ratio"
            :min="0"
            :max="1"
            :step="0.01"
            :precision="2"
            controls-position="right"
            aria-label="训练集比例"
          />
          <b>:</b>
          <el-input
            :model-value="validationRatio"
            data-test="validation-ratio"
            readonly
            aria-label="验证集比例"
          />
        </div>
      </div>

      <div class="estimate">
        预计参与 {{ estimatedVideos }} 个视频 · {{ estimatedFrames }} 个启用帧
      </div>

      <section class="labels-section">
        <header>
          <div class="labels-section-title">
            <strong>YOLO 标签快照</strong><small>导出后不随项目标签变化</small>
          </div>
          <el-radio-group v-model="mode" class="label-mode" data-test="label-mode" size="small">
            <el-radio-button value="project">使用项目标签</el-radio-button>
            <el-radio-button data-test="manual-mode" value="manual">手动调整</el-radio-button>
          </el-radio-group>
        </header>
        <div v-if="labels.length" class="label-list">
          <div v-for="(label, index) in labels" :key="label.source_label_id" class="label-row">
            <code>{{ index }}</code>
            <el-switch
              v-model="label.enabled"
              :data-test="`label-enabled-${label.name}`"
              :disabled="mode !== 'manual'"
              :aria-label="`${label.enabled ? '停用' : '启用'}类别 ${label.name}`"
            />
            <strong>{{ label.name }}</strong>
            <div v-if="mode === 'manual'" class="order-actions">
              <VButton variant="quiet" :data-test="`move-up-${label.name}`"
                :disabled="index === 0"
                :title="`上移 ${label.name}`"
                :aria-label="`上移 ${label.name}`"
                @click="move(index, -1)"/>
              <VButton variant="quiet" :disabled="index === labels.length - 1"
                :title="`下移 ${label.name}`"
                :aria-label="`下移 ${label.name}`"
                @click="move(index, 1)"/>
            </div>
          </div>
        </div>
        <p v-else class="empty-labels">项目还没有标签。</p>
      </section>

      <el-alert
        v-if="validationMessage"
        :title="validationMessage"
        type="warning"
        :closable="false"
      />
    </div>

    <template #footer>
      <VButton variant="secondary" @click="emit('update:modelValue', false)">取消</VButton>
      <VButton variant="primary" data-test="submit-export"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="submit">开始导出</VButton>
    </template>
  </el-dialog>
</template>

<style scoped>
.export-form { display: grid; gap: 17px; }
.field-row { display: grid; grid-template-columns: 148px minmax(0, 1fr); align-items: center; gap: 13px; }
.field-row > span { color: var(--vdw-ink-2); font-size: 14px; }
.ratio-row { grid-template-columns: 148px minmax(120px, 1fr) auto; }
.ratio-inputs { display: grid; grid-template-columns: 110px 13px 110px; align-items: center; gap: 5px; min-width: 0; }
.ratio-inputs b { color: var(--vdw-ink-2); text-align: center; }
.ratio-inputs :deep(.el-input-number) { width: 100%; min-width: 0; }
.ratio-inputs :deep(.el-input__inner) { text-align: center; }
.estimate { padding: 10px 13px; color: var(--vdw-accent); background: var(--vdw-accent-soft); border-left: 3px solid var(--vdw-accent); }
.labels-section { border: 1px solid var(--vdw-line); }
.labels-section > header { display: flex; align-items: center; justify-content: space-between; gap: 13px; padding: 12px 14px; background: var(--vdw-surface-2); border-bottom: 1px solid var(--vdw-line); }
.labels-section-title { display: grid; gap: 2px; }
.labels-section small { color: var(--vdw-ink-2); font-size: 13px; }
.label-mode { flex: none; flex-wrap: nowrap; white-space: nowrap; }
.label-list { max-height: 286px; overflow: auto; }
.label-row { display: grid; grid-template-columns: 38px 48px minmax(0, 1fr) auto; align-items: center; min-height: 45px; padding: 0 13px; border-bottom: 1px solid var(--vdw-surface-3); }
.label-row:last-child { border-bottom: 0; }
.label-row code { color: var(--vdw-ink-2); font: 13px var(--vdw-mono); }
.order-actions { display: flex; }
.empty-labels { margin: 0; padding: 24px; color: var(--vdw-ink-2); text-align: center; }
@media (max-width: 680px) {
  .field-row, .ratio-row { grid-template-columns: 1fr; }
  .ratio-inputs { grid-template-columns: minmax(96px, 1fr) 13px minmax(96px, 1fr); }
  .labels-section > header { align-items: flex-start; flex-direction: column; }
}
</style>
