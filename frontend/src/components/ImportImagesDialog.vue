<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { previewImageImport, importImages, type ImageImportPreview } from '../api/images'
import { listLabels, type ProjectLabel } from '../api/labels'
import ServerFilePicker from './ServerFilePicker.vue'
import VButton from '../ui/VButton.vue'
import { notify } from '../ui/notify'
const props = defineProps<{modelValue: boolean; projectId: string}>()
const emit = defineEmits<{'update:modelValue': [boolean]; submitted: []}>()
const root = ref<string | string[]>('.')
const ignoreAnnotations = ref(false)
const preview = ref<ImageImportPreview | null>(null)
const labels = ref<ProjectLabel[]>([])
const mappings = ref<Array<{source_id: number; sourceName: string; target: string; name: string}>>([])
const confirmed = ref(false)
const busy = ref(false)
const error = ref('')
let generation = 0
let labelGeneration = 0
const canSubmit = computed(() => preview.value && (preview.value.new_images ?? preview.value.total_images)>0 && !preview.value.errors.length && (!preview.value.warnings.length || confirmed.value) && !busy.value)
watch([root, ignoreAnnotations], () => {generation++; preview.value = null; mappings.value = []; confirmed.value = false; error.value = ''})
watch([() => props.modelValue, () => props.projectId], async ([open]) => {
  generation++
  const active = ++labelGeneration
  preview.value = null; mappings.value = []; error.value = ''; confirmed.value = false; labels.value = []
  if (open) {
    busy.value = true
    try {
      const result = await listLabels(props.projectId)
      if (active === labelGeneration) labels.value = result
    } catch (reason) {if (active === labelGeneration) error.value = reason instanceof Error ? reason.message : '标签加载失败'}
    finally {if (active === labelGeneration) busy.value = false}
  }
}, {immediate:true})
async function inspect() {
  if (typeof root.value !== 'string') return
  const active = ++generation
  busy.value = true; error.value = ''; preview.value = null; mappings.value = []; confirmed.value = false
  try {
    const result = await previewImageImport(props.projectId, root.value, ignoreAnnotations.value)
    if (active !== generation || !props.modelValue) return
    preview.value = result
    mappings.value = result.source_classes.map(c => {
      const name = c.name.trim().toLowerCase().replace(/\s+/g, ' ')
      return {source_id: c.source_id, sourceName: c.name, name, target: labels.value.find(l => l.name === name)?.id ?? '__new__'}
    })
  } catch (reason) {if (active === generation) error.value = reason instanceof Error ? reason.message : '预检失败'}
  finally {busy.value = false}
}
async function submit() {
  if (!canSubmit.value || !preview.value || typeof root.value !== 'string') return
  busy.value = true; error.value = ''
  try {
    await importImages(props.projectId, {root_path: root.value, ignore_annotations: ignoreAnnotations.value, fingerprint: preview.value.fingerprint,
      confirm_warnings: confirmed.value, class_mapping: mappings.value.map(m => ({source_id: m.source_id,
        project_label_id: m.target === '__new__' ? null : m.target, new_label_name: m.target === '__new__' ? m.name : null}))})
    notify.success('图片导入任务已创建。')
    emit('submitted'); emit('update:modelValue', false)
  } catch (reason) {error.value = reason instanceof Error ? reason.message : '导入失败'}
  finally {busy.value = false}
}
</script>
<template>
  <el-dialog append-to-body top="6vh" :model-value="modelValue" title="导入图像目录" width="min(1040px, calc(100vw - 32px))" @update:model-value="emit('update:modelValue', $event)">
    <div class="import-form">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <p>自动识别图像目录或 YOLO 目标检测数据集；目录内的标注或配置有误时，请修复后重新预检。</p>
      <label><el-switch v-model="ignoreAnnotations" :disabled="busy" aria-label="不使用目录内的标注和类别" />不使用目录内的标注和类别</label>
      <ServerFilePicker v-if="modelValue" v-model="root" mode="directory" />
      <VButton :loading="busy" @click="inspect">预检当前目录</VButton>
      <template v-if="preview">
        <p data-test="resolved-import-format">识别格式：{{ preview.format === 'yolo_detect' ? 'YOLO 目标检测数据集' : '无标注图像目录' }}</p>
        <p>{{ preview.root_name }} · 扫描 {{ preview.total_images }} 张图片 · 新增 {{ preview.new_images ?? preview.total_images }} 张 · 已存在 {{ preview.existing_images ?? 0 }} 张 · 批内重复 {{ preview.duplicate_images ?? 0 }} 张</p>
        <p>新增图片含 {{ preview.annotation_count }} 个矩形框 · 忽略 {{ preview.ignored_files }} 个附加文件。同内容图片自动跳过，保留系统内已有标注和启停状态；再次导入只补充新图片。</p>
        <el-alert v-if="preview.new_images===0" title="没有可新增的图片，所有图片内容均已存在或在本批次内重复。" type="info" :closable="false" />
        <el-table :data="preview.directories" max-height="220"><el-table-column prop="name" label="导入目录名" /><el-table-column prop="source_relative_path" label="来源目录" /><el-table-column prop="total_images" label="扫描" width="70" /><el-table-column prop="new_images" label="新增" width="70" /><el-table-column prop="existing_images" label="已存在" width="80" /><el-table-column prop="duplicate_images" label="批内重复" width="90" /></el-table>
        <div v-for="mapping in mappings" :key="mapping.source_id" class="mapping-row">
          <span :title="mapping.sourceName">来源类别 {{ mapping.source_id }}：{{ mapping.sourceName }}</span>
          <el-select v-model="mapping.target" aria-label="映射至项目标签"><el-option value="__new__" label="新建项目标签" /><el-option v-for="label in labels" :key="label.id" :value="label.id" :label="label.name" /></el-select>
          <el-input v-if="mapping.target === '__new__'" v-model="mapping.name" placeholder="英文类别名" aria-label="新标签英文名称" />
        </div>
        <div class="issues" v-if="preview.errors.length || preview.warnings.length">
          <p v-for="(issue, index) in [...preview.errors, ...preview.warnings]" :key="index">{{ issue.path }}：{{ issue.message }}</p>
        </div>
        <el-checkbox v-if="preview.warnings.length" v-model="confirmed">已确认缺标注、重复图片或其他预检警告</el-checkbox>
        <el-alert v-if="preview.errors.length" title="请修复来源错误后重新预检。未导入任何图片。" type="error" :closable="false" />
      </template>
    </div>
    <template #footer><VButton @click="emit('update:modelValue', false)">取消</VButton><VButton variant="primary" :disabled="!canSubmit" :loading="busy" @click="submit">创建导入任务</VButton></template>
  </el-dialog>
</template>
<style scoped>
.import-form {display:grid;gap:14px;max-height:calc(90vh - 150px);overflow-y:auto}.import-form>label {display:flex;align-items:center;gap:20px}.mapping-row{display:grid;grid-template-columns:130px 240px 1fr;gap:12px;align-items:center}.mapping-row>span{min-width:0;overflow-wrap:anywhere}.issues{max-height:170px;overflow:auto;padding:12px;background:var(--vdw-surface-2);font-size:13px}.issues p{margin:4px 0}
</style>
