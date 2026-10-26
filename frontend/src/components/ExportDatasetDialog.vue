<script setup lang="ts">
import { ElMessageBox } from 'element-plus'
import { Bottom, Top } from '@element-plus/icons-vue'
import { notify } from '../ui/notify'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import {
  createDatasetExport, previewDatasetExport,
  type DirectoryRule, type ImageExportPreview,
  type DatasetExport,
  type DatasetExportLabel,
} from '../api/datasetExports'
import { getProject } from '../api/projects'
import { listImageDirectories, previewImageDuplicates, disableDuplicateImages, type ImageDirectory } from '../api/images'
import { listLabels } from '../api/labels'
import { listVideos } from '../api/media'
import VButton from '../ui/VButton.vue'

const props = defineProps<{ modelValue: boolean; projectId: string }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submitted: [value: DatasetExport]
  'source-updated': []
}>()
const isImage = ref(false)
const directories = ref<ImageDirectory[]>([])
const rules = ref<DirectoryRule[]>([])
const directoryById = computed(() => Object.fromEntries(directories.value.map(directory => [directory.id, directory])))
const splitSeed = ref(0)
const splitWarningMessages = {
  insufficient_samples: '不足两张，无法同时分配训练集和验证集',
  fixed_roles: '受固定目录规则约束',
  exact_content_groups: '受重复图像不可拆分约束',
}
const preview = ref<ImageExportPreview | null>(null)
const previewError = ref('')
const previewLoading = ref(false)
const duplicateBusy = ref(false)
const duplicateError = ref('')
const duplicateConflict = computed(() => /重复|完全相同|duplicate/i.test(previewError.value || error.value))
let loadVersion = 0
let previewVersion = 0
let previewTimer: ReturnType<typeof setTimeout> | undefined
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
  && !duplicateBusy.value
  && (!isImage.value || (Boolean(preview.value?.total_samples) && !previewLoading.value && !previewError.value))
))

function move(index: number, offset: -1 | 1) {
  const target = index + offset
  if (target < 0 || target >= labels.value.length) return
  const reordered = [...labels.value]
  ;[reordered[index], reordered[target]] = [reordered[target], reordered[index]]
  labels.value = reordered.map((label, mapping) => ({ ...label, mapping }))
}

async function load() {
  const active = ++loadVersion
  const projectId = props.projectId
  loading.value = true
  error.value = ''
  name.value = ''
  labels.value = []; directories.value = []; rules.value = []
  isImage.value = false; splitSeed.value = 0
  trainRatio.value = 0.8
  mode.value = 'project'
  const current = () => active === loadVersion && props.modelValue && props.projectId === projectId
  try {
    const [project, projectLabels] = await Promise.all([getProject(projectId), listLabels(projectId)])
    if (!current()) return
    const imageProject = project.project_type === 'image'
    const groups = imageProject ? await listImageDirectories(projectId) : null
    const videos = imageProject ? null : await listVideos(projectId, 1, 999)
    if (!current()) return
    isImage.value = imageProject
    labels.value = projectLabels.map((label, mapping) => ({
      source_label_id: label.id, name: label.name, mapping, enabled: label.enabled,
    }))
    if (groups) {
      directories.value = groups
      rules.value = groups.map(d => ({directory_id:d.id, included:true, mode:'ratio', train_ratio:null}))
    } else if (videos) {
      const included = videos.items.filter(video => video.status === 'ready' && video.enabled && (video.sampling?.extracted_frames ?? 0) > 0)
      estimatedVideos.value = included.length
      estimatedFrames.value = included.reduce((total, video) => total + (video.sampling?.enabled_frames ?? 0), 0)
    }
  } catch (reason) {
    if (current()) error.value = reason instanceof Error ? reason.message : '导出配置加载失败'
  } finally {
    if (current()) {
      loading.value = false
      if (isImage.value && !error.value) void refreshPreview()
    }
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
      ...(isImage.value ? {directory_rules:rules.value, split_seed:splitSeed.value, preview_fingerprint:preview.value?.fingerprint} : {}),
    })
    notify.success('数据集导出任务已创建。')
    emit('submitted', created)
    emit('update:modelValue', false)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '数据集导出任务创建失败'
  } finally {
    submitting.value = false
  }
}

async function refreshPreview() {
  if (previewTimer) clearTimeout(previewTimer)
  const active = ++previewVersion
  preview.value = null; previewError.value = ''; previewLoading.value = false
  if (!isImage.value || !props.modelValue || loading.value || validationMessage.value) return
  previewLoading.value = true
  try {
    const value = await previewDatasetExport(props.projectId, {name:name.value.trim() || '预览', train_ratio:trainRatio.value,
      labels:labels.value, directory_rules:rules.value, split_seed:splitSeed.value})
    if (!value.positive_samples || !value.negative_samples || !value.target_positive_samples || !value.target_negative_samples) {
      throw new Error('服务端未返回正负样本划分统计，请更新服务后重新计算。')
    }
    if (active === previewVersion && props.modelValue) preview.value = value
  } catch (reason) {if(active === previewVersion) previewError.value = reason instanceof Error ? reason.message : '划分预览失败'}
  finally {if(active === previewVersion) previewLoading.value = false}
}
async function disableDuplicates() {
  if (duplicateBusy.value) return
  const active = loadVersion
  const projectId = props.projectId
  const current = () => active === loadVersion && props.modelValue && props.projectId === projectId
  duplicateBusy.value = true; duplicateError.value = ''
  let updated = false
  try {
    const duplicates = await previewImageDuplicates(projectId)
    if (!current()) return
    if (!duplicates.duplicate_count) {
      notify.success('项目内当前启用的图像没有重复项。')
      const groups = await listImageDirectories(projectId)
      if (!current()) return
      directories.value = groups
      await refreshPreview()
      return
    }
    try {
      await ElMessageBox.confirm(
        `项目内当前启用图像中发现 ${duplicates.group_count} 组重复图像，将停用 ${duplicates.duplicate_count} 张。每组按目录顺序、相对路径、ID 稳定保留首张，其余仅停用，不删除图像或标注，也不启用已停用图像。此操作涵盖整个项目。`,
        '确认停用重复图像',
        {confirmButtonText: '确认停用', cancelButtonText: '取消', type: 'warning'},
      )
    } catch {return}
    if (!current()) return
    const result = await disableDuplicateImages(projectId, duplicates.fingerprint)
    if (!current()) return
    updated = true
    previewVersion++; preview.value = null
    error.value = ''
    emit('source-updated')
    notify.success(`已停用 ${result.disabled_count} 张重复图像，保留全部标注。`)
    const groups = await listImageDirectories(projectId)
    if (!current()) return
    directories.value = groups
  } catch (reason) {
    if (current()) duplicateError.value = reason instanceof Error ? reason.message : '重复图像处理失败，请重试'
  } finally {
    if (current()) {
      if (updated) await refreshPreview()
      if (current()) duplicateBusy.value = false
    }
  }
}
watch([rules, trainRatio, labels, splitSeed], () => {
  previewVersion++; preview.value=null
  previewLoading.value=isImage.value && props.modelValue && !loading.value && !validationMessage.value
  if(previewTimer)clearTimeout(previewTimer)
  previewTimer=setTimeout(refreshPreview,250)
}, {deep:true, flush:'sync'})
onBeforeUnmount(() => {loadVersion++;previewVersion++;if(previewTimer)clearTimeout(previewTimer)})
watch([() => props.modelValue, () => props.projectId], ([open]) => {
  loadVersion++; previewVersion++; preview.value=null; previewLoading.value=false
  duplicateBusy.value=false; duplicateError.value=''
  if(previewTimer)clearTimeout(previewTimer)
  if (open) void load()
}, { immediate: true })
</script>

<template>
  <el-dialog
    append-to-body
    :model-value="modelValue"
    title="导出数据集"
    :width="isImage ? '1060px' : '760px'"
    :show-close="!submitting && !duplicateBusy"
    :close-on-click-modal="!submitting && !duplicateBusy"
    :close-on-press-escape="!submitting && !duplicateBusy"
    @update:model-value="!submitting && !duplicateBusy && emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="export-form" :class="{ 'image-export-form': isImage }">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />

      <label class="field-row">
        <span>数据集名称</span>
        <el-input
          v-model="name"
          data-test="dataset-name"
          maxlength="128"
          placeholder="例如: testset-v1"
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

      <div v-if="!isImage" class="estimate">
        预计参与 {{ estimatedVideos }} 个视频 · {{ estimatedFrames }} 个启用帧
      </div>

      <section v-if="isImage" class="directory-rules">
        <h3>目录划分</h3><p>来源目录只用于分组。每次导出时决定是否参与、使用训练集或验证集、按比例划分。</p>
        <div v-for="rule in rules" :key="rule.directory_id" class="directory-rule">
          <el-checkbox v-model="rule.included" :aria-label="`参与导出 ${directoryById[rule.directory_id]?.name}`" />
          <div class="directory-info"><strong>{{ directoryById[rule.directory_id]?.name }}</strong><small>{{ directoryById[rule.directory_id]?.source_relative_path }}</small><small>总数 {{ directoryById[rule.directory_id]?.total_images ?? 0 }} · 待标注 {{ (directoryById[rule.directory_id]?.total_images ?? 0) - (directoryById[rule.directory_id]?.labeled_images ?? 0) }} · 停用 {{ (directoryById[rule.directory_id]?.total_images ?? 0) - (directoryById[rule.directory_id]?.enabled_images ?? 0) }}</small></div>
          <el-select v-model="rule.mode" :disabled="!rule.included" aria-label="目录划分方式" @change="rule.train_ratio=null"><el-option value="train" label="全部训练集"/><el-option value="val" label="全部验证集"/><el-option value="ratio" label="按比例划分"/></el-select>
          <el-select :model-value="rule.train_ratio === null ? 'shared' : 'own'" :disabled="!rule.included || rule.mode!=='ratio'" aria-label="目录比例来源" @change="(value: string)=>rule.train_ratio=value==='shared' ? null : trainRatio"><el-option value="shared" label="沿用全局"/><el-option value="own" label="独立设置"/></el-select>
          <el-input-number v-if="rule.mode==='ratio' && rule.train_ratio!==null" v-model="rule.train_ratio" :min="0" :max="1" :step="0.01" :precision="2" aria-label="目录训练比例"/>
        </div>
        <label>划分种子 <el-input-number v-model="splitSeed" :min="0" :max="2147483647" aria-label="划分种子"/></label>
        <div v-loading="previewLoading" class="estimate" data-test="image-export-preview" :aria-busy="previewLoading" role="status" aria-live="polite">
          <p v-if="previewLoading">正在计算目录划分…</p>
          <el-alert v-else-if="previewError" :title="previewError" type="error" :closable="false"/>
          <template v-else-if="preview">
          <p v-if="!preview.total_samples">没有可导出的有效图片，请检查启用状态、文件和目录规则。</p>
          <strong>实际划分：训练 {{ preview.train_samples }} · 验证 {{ preview.val_samples }} · 训练比例 {{ (preview.actual_train_ratio*100).toFixed(1) }}%</strong>
          <p data-test="image-export-strata">正样本：训练 {{ preview.positive_samples.train }} / 目标 {{ preview.target_positive_samples.train }}，验证 {{ preview.positive_samples.val }} / 目标 {{ preview.target_positive_samples.val }}；负样本：训练 {{ preview.negative_samples.train }} / 目标 {{ preview.target_negative_samples.train }}，验证 {{ preview.negative_samples.val }} / 目标 {{ preview.target_negative_samples.val }}。</p>
          <div v-for="stat in preview.directory_stats" :key="stat.directory_id" class="directory-stat">
            <p>{{ stat.name }}：有效 {{ stat.effective_images }}，训练 {{ stat.train_images }}，验证 {{ stat.val_images }}</p>
            <p>正样本 {{ stat.positive_images }}：训练 {{ stat.train_positive_images }} / 目标 {{ stat.target_train_positive_images }}，验证 {{ stat.val_positive_images }} / 目标 {{ stat.target_val_positive_images }}；负样本 {{ stat.negative_images }}：训练 {{ stat.train_negative_images }} / 目标 {{ stat.target_train_negative_images }}，验证 {{ stat.val_negative_images }} / 目标 {{ stat.target_val_negative_images }}。</p>
            <p v-if="stat.positive_deviation || stat.negative_deviation">受样本不足、重复分组或固定规则约束，训练目标偏差：正样本 {{ stat.positive_deviation }}，负样本 {{ stat.negative_deviation }}。</p>
          </div>
          <p v-for="warning in preview.stratification_warnings" :key="`${warning.directory_id}-${warning.kind}`" class="split-warning">{{ directoryById[warning.directory_id]?.name ?? warning.directory_id }}：{{ warning.kind === 'positive' ? '正样本' : '负样本' }}{{ splitWarningMessages[warning.reason] }}。</p>
          <p>排除：停用 {{ preview.excluded.disabled ?? 0 }}，目录不参与 {{ preview.excluded.directory_excluded ?? 0 }}，文件不可用 {{ preview.excluded.file_unavailable ?? 0 }}。过滤 {{ preview.filtered_annotations }} 个类别框。</p>
          <small>{{ preview.single_training_hint }}</small>
          </template>
          <p data-test="image-export-negative-hint">启用且可用、无目标框的图片（包括尚未标注图片）导出为负样本；含目标但尚未标注时，请先补标注，或停用图片 / 排除目录。正负样本按本次保留类别统计并分别划分。</p>
          <div class="preview-actions">
            <VButton data-test="retry-image-export-preview" :disabled="previewLoading || duplicateBusy || loading" title="仅重新计算预览，不修改图像、标注或启用状态" @click="refreshPreview">重新计算划分</VButton>
            <VButton v-if="duplicateConflict || duplicateError" data-test="disable-duplicate-images" :loading="duplicateBusy" :disabled="previewLoading || loading" @click="disableDuplicates">一键停用重复图像</VButton>
          </div>
          <el-alert v-if="duplicateError" :title="duplicateError" type="error" :closable="false"/>
        </div>
      </section>

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
              <VButton
                variant="quiet"
                size="sm"
                icon-only
                :data-test="`move-up-${label.name}`"
                :disabled="index === 0"
                :label="`上移 ${label.name}`"
                :title="`上移 ${label.name}`"
                @click="move(index, -1)"
              ><template #icon><el-icon><Top /></el-icon></template></VButton>
              <VButton
                variant="quiet"
                size="sm"
                icon-only
                :disabled="index === labels.length - 1"
                :label="`下移 ${label.name}`"
                :title="`下移 ${label.name}`"
                @click="move(index, 1)"
              ><template #icon><el-icon><Bottom /></el-icon></template></VButton>
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
      <VButton variant="default" :disabled="submitting || duplicateBusy" @click="emit('update:modelValue', false)">取消</VButton>
      <VButton variant="primary" data-test="submit-export"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="submit">开始导出</VButton>
    </template>
  </el-dialog>
</template>

<style scoped>
.split-warning{color:var(--vdw-warn)}
.preview-actions{display:flex;gap:10px;margin-top:10px}
.directory-rules{display:grid;gap:12px}.directory-rules h3,.directory-rules p{margin:0}.directory-rule{display:grid;grid-template-columns:26px minmax(140px,1fr) 150px 130px 150px;align-items:center;gap:10px}.directory-info{display:grid;gap:3px;min-width:0}.directory-info small{font-size:13px;color:var(--vdw-ink-2);overflow-wrap:anywhere}.directory-rules>label{display:flex;align-items:center;gap:14px}
.image-export-form { max-height: calc(80vh - 150px); overflow-y: auto; padding-right: 4px; }
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
