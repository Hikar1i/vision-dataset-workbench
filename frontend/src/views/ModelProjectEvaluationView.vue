<script setup lang="ts">
import { Delete, Plus, Refresh, UploadFilled, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { can } from '../api/access'

import { getModelProject, listModelProjectModels, type InferenceModel, type ModelProject } from '../api/models'
import { listModelArtifacts, type ModelArtifact } from '../api/modelArtifacts'
import {
  createModelEvaluation,
  deleteEvaluationDataset,
  evaluationPlotUrl,
  listEvaluationDatasets,
  listModelEvaluations,
  uploadEvaluationDataset,
  type EvaluationDataset,
  type ModelEvaluation,
} from '../api/modelEvaluations'
import PageHeader from '../components/PageHeader.vue'
import { modelCapabilityBackTarget } from '../navigation/modelCapabilitySource'
import VButton from '../ui/VButton.vue'
import VEmpty from '../ui/VEmpty.vue'
import VPanel from '../ui/VPanel.vue'
import VRow from '../ui/VRow.vue'
import VTable from '../ui/VTable.vue'
import VTag from '../ui/VTag.vue'

const route = useRoute()
const projectId = computed(() => String(route.params.id))
const project = ref<ModelProject>()
const models = ref<InferenceModel[]>([])
const datasets = ref<EvaluationDataset[]>([])
const evaluations = ref<ModelEvaluation[]>([])
const tab = ref<'records' | 'datasets'>('records')
const loading = ref(false)
const importOpen = ref(false)
const evaluationOpen = ref(false)
const detail = ref<ModelEvaluation>()
const datasetName = ref('')
const datasetFile = ref<File>()
const modelId = ref('')
const datasetId = ref('')
const format = ref<ModelEvaluation['format']>('pt')
const artifacts = ref<ModelArtifact[]>([])
const submitting = ref(false)
let poll: number | undefined

const RECORD_COLUMNS = 'minmax(190px,1.2fr) minmax(160px,1fr) 92px 100px 110px 132px'
const DATASET_COLUMNS = 'minmax(190px,1.2fr) 90px 96px minmax(180px,1fr) 110px 120px'
const active = computed(() =>
  evaluations.value.some((item) => ['queued', 'running'].includes(item.status))
  || datasets.value.some((item) => ['queued', 'validating'].includes(item.status)),
)
const readyDatasets = computed(() => datasets.value.filter((item) => item.status === 'ready'))
const readyModels = computed(() => models.value.filter((item) => item.status === 'ready'))
const canExecute = computed(() => can(project.value?.access, 'task.execute'))
const canUpdate = computed(() => can(project.value?.access, 'project.update'))
const formats = computed(() => [
  { value: 'pt' as const, label: 'PyTorch (.pt)', enabled: true },
  { value: 'onnx' as const, label: 'ONNX', enabled: artifacts.value.some((item) => item.format === 'onnx' && item.status === 'ready') },
  { value: 'engine' as const, label: 'TensorRT (.engine)', enabled: artifacts.value.some((item) => item.format === 'engine' && item.status === 'ready') },
])
const backTarget = computed(() => modelCapabilityBackTarget(
  projectId.value,
  typeof route.query.modelId === 'string' ? route.query.modelId : undefined,
  route.query.source,
  { to: '/model-projects', label: '返回模型项目' },
))
const evaluationQuery = computed(() => ({
  ...(typeof route.query.modelId === 'string' ? { modelId: route.query.modelId } : {}),
  ...(['models', 'detail'].includes(String(route.query.source)) ? { source: String(route.query.source) } : {}),
}))

const STATUS: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' | 'idle' }> = {
  queued: { label: '排队中', tone: 'warn' }, validating: { label: '校验中', tone: 'warn' },
  running: { label: '评估中', tone: 'warn' }, ready: { label: '可用', tone: 'ok' },
  succeeded: { label: '已完成', tone: 'ok' }, failed: { label: '失败', tone: 'danger' },
  canceled: { label: '已取消', tone: 'idle' },
}
const status = (value: string) => STATUS[value] ?? { label: value, tone: 'idle' as const }
const percent = (value: unknown) => typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '—'

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    ;[project.value, models.value, datasets.value, evaluations.value] = await Promise.all([
      getModelProject(projectId.value),
      listModelProjectModels(projectId.value),
      listEvaluationDatasets(projectId.value),
      listModelEvaluations(projectId.value),
    ])
    const requestedModel = String(route.query.modelId || '')
    if (!modelId.value && readyModels.value.some((item) => item.id === requestedModel)) {
      modelId.value = requestedModel
      await modelChanged(requestedModel)
    }
    if (active.value && !poll) poll = window.setInterval(() => load(true), 2000)
    if (!active.value && poll) { window.clearInterval(poll); poll = undefined }
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '评估页面加载失败')
  } finally { loading.value = false }
}

function pickDataset(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.zip')) return void ElMessage.error('只支持 ZIP 文件。')
  if (file.size > 1024 * 1024 * 1024) return void ElMessage.error('ZIP 不能超过 1 GB。')
  datasetFile.value = file
  if (!datasetName.value) datasetName.value = file.name.replace(/\.zip$/i, '')
}

async function importDataset() {
  if (!datasetFile.value || !datasetName.value.trim()) return
  submitting.value = true
  try {
    const created = await uploadEvaluationDataset(projectId.value, datasetName.value.trim(), datasetFile.value)
    datasets.value.unshift(created.dataset)
    importOpen.value = false
    datasetFile.value = undefined
    datasetName.value = ''
    ElMessage.success('测试集已上传，正在后台校验。')
    void load(true)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '测试集上传失败')
  } finally { submitting.value = false }
}

async function modelChanged(value: string) {
  artifacts.value = value ? await listModelArtifacts(value) : []
  if (!formats.value.find((item) => item.value === format.value)?.enabled) format.value = 'pt'
}

async function createEvaluation() {
  if (!modelId.value || !datasetId.value) return
  submitting.value = true
  try {
    const created = await createModelEvaluation(projectId.value, modelId.value, datasetId.value, format.value)
    evaluations.value.unshift(created.evaluation)
    evaluationOpen.value = false
    ElMessage.success('评估任务已创建。')
    void load(true)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '评估任务创建失败')
  } finally { submitting.value = false }
}

async function removeDataset(item: EvaluationDataset) {
  try {
    await ElMessageBox.confirm(`删除测试集“${item.name}”？历史评估记录仍保留快照信息。`, '删除测试集', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  try {
    await deleteEvaluationDataset(item.id)
    datasets.value = datasets.value.filter((value) => value.id !== item.id)
    ElMessage.success('测试集已删除。')
  } catch (reason) { ElMessage.error(reason instanceof Error ? reason.message : '测试集删除失败') }
}

watch(projectId, () => load(), { immediate: true })
onBeforeUnmount(() => { if (poll) window.clearInterval(poll) })
</script>

<template>
  <main class="content-page">
    <PageHeader
      :title="project?.name || '模型评估'"
      kind="model project"
      :code="project ? project.id.slice(0, 6).toUpperCase() : undefined"
      :back-to="backTarget.to"
      :back-label="backTarget.label"
    >
      <template #meta>
        <span>{{ evaluations.length }} 条评估</span><span>{{ readyDatasets.length }} 个可用测试集</span>
      </template>
      <template #tabs>
        <RouterLink :to="`/model-projects/${projectId}/models`">模型列表</RouterLink>
        <RouterLink :to="{ path: `/model-projects/${projectId}/evaluations`, query: evaluationQuery }">模型评估</RouterLink>
      </template>
    </PageHeader>

    <div v-loading="loading" class="content-body evaluation-body">
      <div class="subnav">
        <button :class="{ active: tab === 'records' }" @click="tab = 'records'">评估记录</button>
        <button :class="{ active: tab === 'datasets' }" @click="tab = 'datasets'">测试集管理</button>
      </div>

      <template v-if="tab === 'records'">
        <div class="toolbar evaluation-toolbar">
          <span>固定参数：conf 0.001 · IOU 0.70 · batch 1 · max_det 300</span>
          <div class="toolbar-actions"><VButton :loading="loading" @click="load()"><template #icon><el-icon><Refresh /></el-icon></template>刷新</VButton><VButton v-if="canExecute" variant="primary" :disabled="!readyModels.length || !readyDatasets.length" :title="!readyModels.length ? '暂无可用模型' : !readyDatasets.length ? '请先导入并校验测试集' : '新建评估'" @click="evaluationOpen = true"><template #icon><el-icon><Plus /></el-icon></template>新建评估</VButton></div>
        </div>
        <VPanel flush><VTable :columns="RECORD_COLUMNS" :headers="['模型', '测试集', '格式', '状态', 'mAP50-95', '操作']">
          <VRow v-for="item in evaluations" :key="item.id" :columns="RECORD_COLUMNS">
            <div class="cell-main"><strong>{{ item.model_name }} <small v-if="item.model_deleted">已删除</small></strong><span>{{ item.created_at.slice(0,16).replace('T',' ') }}</span></div>
            <div class="cell-main"><strong>{{ item.dataset_name }} <small v-if="item.dataset_deleted">已删除</small></strong><span class="mono">{{ item.dataset_sha256.slice(0,10) }}</span></div>
            <VTag tone="idle">{{ item.format.toUpperCase() }}</VTag>
            <VTag :tone="status(item.status).tone" :title="item.error || undefined">{{ status(item.status).label }}</VTag>
            <span class="metric">{{ percent(item.metrics.map50_95) }}</span>
            <VButton size="sm" :disabled="item.status !== 'succeeded'" :title="item.status !== 'succeeded' ? '评估完成后可查看详情' : '查看评估详情'" @click="detail = item"><template #icon><el-icon><View /></el-icon></template>详情</VButton>
          </VRow>
          <template #empty><VEmpty v-if="!evaluations.length" title="暂无评估记录" note="先导入测试集，再为具体模型创建一次可复现评估。" /></template>
        </VTable></VPanel>
      </template>

      <template v-else>
        <div class="toolbar evaluation-toolbar">
          <span>测试集为不可变内容快照；同项目内按内容哈希去重。</span>
          <div class="toolbar-actions"><VButton :loading="loading" @click="load()"><template #icon><el-icon><Refresh /></el-icon></template>刷新</VButton><VButton v-if="canExecute" variant="primary" @click="importOpen = true"><template #icon><el-icon><UploadFilled /></el-icon></template>导入测试集</VButton></div>
        </div>
        <VPanel flush><VTable :columns="DATASET_COLUMNS" :headers="['测试集', '图像', '类别', '内容哈希', '状态', '操作']">
          <VRow v-for="item in datasets" :key="item.id" :columns="DATASET_COLUMNS">
            <div class="cell-main"><strong>{{ item.name }}</strong><span>{{ item.created_at.slice(0,10) }}</span></div>
            <span class="metric">{{ item.image_count }}</span><span class="metric">{{ item.classes.length }}</span>
            <span class="mono ellipsis" :title="item.content_sha256 || ''">{{ item.content_sha256 || '校验后生成' }}</span>
            <VTag :tone="status(item.status).tone" :title="item.error || undefined">{{ status(item.status).label }}</VTag>
            <VButton v-if="canUpdate" variant="danger" size="sm" :disabled="['queued','validating'].includes(item.status)" :title="['queued','validating'].includes(item.status) ? '测试集校验期间不可删除' : '删除测试集'" @click="removeDataset(item)"><template #icon><el-icon><Delete /></el-icon></template>删除</VButton>
          </VRow>
          <template #empty><VEmpty v-if="!datasets.length" title="还没有测试集" note="上传结构受控的 ZIP 后，系统会在后台完成安全校验。" /></template>
        </VTable></VPanel>
      </template>
    </div>

    <el-dialog v-model="importOpen" title="导入评估测试集" width="720px">
      <div class="import-layout">
        <div class="zip-example">
          <strong>ZIP 目录结构</strong>
          <pre>classes.txt&#10;images/&#10;  image-001.jpg&#10;labels/&#10;  image-001.txt</pre>
          <p>允许额外包一层目录。负样本也必须有同名空 TXT。限制：ZIP 1 GB、解压 5 GB、5000 张图片。</p>
        </div>
        <div class="dialog-fields">
          <label>测试集名称<el-input v-model="datasetName" maxlength="128" /></label>
          <label class="file-drop">选择 ZIP<input type="file" accept=".zip,application/zip" @change="pickDataset" /><span>{{ datasetFile?.name || '点击选择文件' }}</span></label>
        </div>
      </div>
      <template #footer><VButton variant="quiet" @click="importOpen = false">取消</VButton><VButton variant="primary" :loading="submitting" :disabled="!datasetFile || !datasetName.trim()" :title="!datasetFile ? '请选择 ZIP 文件' : !datasetName.trim() ? '请填写测试集名称' : '上传并校验'" @click="importDataset">上传并校验</VButton></template>
    </el-dialog>

    <el-dialog v-model="evaluationOpen" title="新建模型评估" width="620px">
      <div class="dialog-fields">
        <label>模型<el-select v-model="modelId" filterable @change="modelChanged"><el-option v-for="item in readyModels" :key="item.id" :label="item.name" :value="item.id" /></el-select></label>
        <label>测试集<el-select v-model="datasetId" filterable><el-option v-for="item in readyDatasets" :key="item.id" :label="`${item.name} · ${item.image_count} 张`" :value="item.id" /></el-select></label>
        <label>模型格式<el-select v-model="format"><el-option v-for="item in formats" :key="item.value" :label="item.label" :value="item.value" :disabled="!item.enabled" /></el-select></label>
        <el-alert title="评估参数固定以保证不同模型结果可直接比较。" type="info" :closable="false" show-icon />
      </div>
      <template #footer><VButton variant="quiet" @click="evaluationOpen = false">取消</VButton><VButton variant="primary" :loading="submitting" :disabled="!modelId || !datasetId" :title="!modelId ? '请选择模型' : !datasetId ? '请选择测试集' : '开始评估'" @click="createEvaluation">开始评估</VButton></template>
    </el-dialog>

    <el-dialog :model-value="!!detail" title="评估详情" width="min(1040px, calc(100vw - 40px))" @update:model-value="!$event && (detail = undefined)">
      <template v-if="detail">
        <div class="metric-grid"><div v-for="item in [['Precision',detail.metrics.precision],['Recall',detail.metrics.recall],['mAP50',detail.metrics.map50],['mAP50-95',detail.metrics.map50_95]]" :key="String(item[0])"><span>{{ item[0] }}</span><strong>{{ percent(item[1]) }}</strong></div></div>
        <div class="plot-grid"><figure v-if="detail.has_confusion_matrix"><img :src="evaluationPlotUrl(detail.id,'confusion')" alt="归一化混淆矩阵" /><figcaption>归一化混淆矩阵</figcaption></figure><figure v-if="detail.has_pr_curve"><img :src="evaluationPlotUrl(detail.id,'pr-curve')" alt="PR Curve" /><figcaption>PR Curve</figcaption></figure></div>
        <VTable columns="90px minmax(180px,1fr) 130px" :headers="['索引','类别','mAP50-95']"><VRow v-for="item in detail.per_class_metrics" :key="item.class_index" columns="90px minmax(180px,1fr) 130px"><span class="mono">{{ item.class_index }}</span><span>{{ item.class_name }}</span><span class="metric">{{ percent(item.map50_95) }}</span></VRow></VTable>
      </template>
    </el-dialog>
  </main>
</template>

<style scoped>
.evaluation-body{display:grid;gap:14px;align-content:start}.subnav{display:flex;gap:4px;padding:4px;width:fit-content;background:var(--vdw-surface-2);border:1px solid var(--vdw-line);border-radius:var(--vdw-radius-control)}.subnav button{height:32px;padding:0 14px;border:0;border-radius:calc(var(--vdw-radius-control) - 2px);color:var(--vdw-ink-2);background:transparent;cursor:pointer;font:500 14px/1 var(--vdw-sans)}.subnav button.active{color:var(--vdw-ink);background:var(--vdw-surface);box-shadow:var(--vdw-shadow-1)}.toolbar{display:flex;align-items:center;justify-content:space-between;min-height:38px;color:var(--vdw-ink-3);font-size:14px}.toolbar-actions{display:flex;gap:8px}.cell-main{min-width:0}.cell-main strong,.cell-main span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.cell-main span{margin-top:4px;color:var(--vdw-ink-3);font-size:13px}.mono{font-family:var(--vdw-mono)}.ellipsis{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.metric{font:600 14px/1 var(--vdw-mono)}.import-layout{display:grid;grid-template-columns:260px 1fr;gap:22px}.zip-example{padding:16px;background:#10181c;border-radius:var(--vdw-radius-card);color:#dbe4e7}.zip-example pre{margin:12px 0;color:#83d2df;font:13px/1.55 var(--vdw-mono)}.zip-example p{margin:0;color:#9eafb5;font-size:13px;line-height:1.55}.dialog-fields{display:grid;gap:18px}.dialog-fields label{display:grid;gap:8px;color:var(--vdw-ink-2);font-size:14px}.file-drop{padding:18px;border:1px dashed var(--vdw-line-strong);border-radius:var(--vdw-radius-control);cursor:pointer}.file-drop input{position:absolute;width:1px;height:1px;opacity:0}.file-drop span{color:var(--vdw-accent-ink)}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.metric-grid div{padding:14px;border:1px solid var(--vdw-line);border-radius:var(--vdw-radius-control);background:var(--vdw-surface-2)}.metric-grid span,.metric-grid strong{display:block}.metric-grid span{color:var(--vdw-ink-3);font-size:13px}.metric-grid strong{margin-top:6px;font:600 22px/1 var(--vdw-mono)}.plot-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:18px}.plot-grid figure{margin:0;padding:10px;border:1px solid var(--vdw-line);border-radius:var(--vdw-radius-card)}.plot-grid img{display:block;width:100%;max-height:360px;object-fit:contain}.plot-grid figcaption{margin-top:8px;color:var(--vdw-ink-3);text-align:center;font-size:13px}
.cell-main small{margin-left:5px;color:var(--vdw-danger);font-size:13px;font-weight:500}
</style>
