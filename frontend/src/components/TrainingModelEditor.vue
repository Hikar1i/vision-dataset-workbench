<script setup lang="ts">
import { ArrowDown, ArrowUp, Bottom, Delete, Top } from "@element-plus/icons-vue";
import { computed, ref } from "vue";
import type { GpuDevice, TrainingModelDraft, TrainingResources } from "../api/training";
import {
  artifactPreview,
  effectiveResourceIds,
  groupedOptions,
  type TrainingDefaults,
} from "./trainingResources";
import VButton from '../ui/VButton.vue'

const props = defineProps<{
  models: TrainingModelDraft[];
  resources: TrainingResources;
  devices: GpuDevice[];
  mode: string;
  taskCode: string;
  defaults: TrainingDefaults;
}>();
const emit = defineEmits<{
  change: [TrainingModelDraft[]];
  configureMapping: [TrainingModelDraft];
}>();
const rowKeys = new WeakMap<object, string>();
const collapsed = ref<TrainingModelDraft[]>([]);
const cascaderProps = { emitPath: false };
let nextRowKey = 1;

const columns = computed(() => [0, 1].map((column) =>
  props.models.map((row, index) => ({ row, index })).filter(({ index }) => index % 2 === column),
));
const datasetOptions = computed(() => groupedOptions(props.resources.datasets));
const baseModelOptions = computed(() => groupedOptions(props.resources.base_models));

function keyFor(row: TrainingModelDraft) {
  let key = rowKeys.get(row);
  if (!key) {
    key = `training-model-row-${nextRowKey++}`;
    rowKeys.set(row, key);
  }
  return key;
}
function update() { emit("change", [...props.models]); }
function remove(index: number) {
  if (props.models.length <= 1) return;
  props.models.splice(index, 1);
  normalize();
  update();
}
function move(index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= props.models.length) return;
  [props.models[index], props.models[target]] = [props.models[target], props.models[index]];
  normalize();
  update();
}
function normalize() {
  if (props.mode === "custom_sequence") return;
  props.models.forEach((row, index) => {
    row.queue_order = index + 1;
    if (props.mode === "single_device_serial") row.gpu_index = props.models[0]?.gpu_index ?? 0;
  });
}
function toggle(row: TrainingModelDraft) {
  collapsed.value = collapsed.value.includes(row)
    ? collapsed.value.filter((item) => item !== row)
    : [...collapsed.value, row];
}
function templateFor(row: TrainingModelDraft) {
  const id = effectiveResourceIds(row, props.defaults).templateId;
  return props.resources.templates.find((item) => item.id === id);
}
function overrideEnabled(row: TrainingModelDraft) {
  return row.epochs_override != null || row.batch_mode_override != null || row.image_size_override != null;
}
function setOverride(row: TrainingModelDraft, enabled: boolean) {
  if (!enabled) {
    row.epochs_override = null;
    row.batch_mode_override = null;
    row.batch_value_override = null;
    row.image_size_override = null;
  } else {
    const template = templateFor(row);
    if (!template) return;
    row.epochs_override = template.epochs;
    row.batch_mode_override = template.batch_mode as TrainingModelDraft["batch_mode_override"];
    row.batch_value_override = template.batch_value;
    row.image_size_override = template.image_size;
  }
  update();
}
function setBatchMode(row: TrainingModelDraft, mode: TrainingModelDraft["batch_mode_override"]) {
  row.batch_mode_override = mode;
  row.batch_value_override = mode === "auto" ? null : mode === "fixed" ? 10 : 0.8;
  update();
}
function summary(row: TrainingModelDraft) {
  const ids = effectiveResourceIds(row, props.defaults);
  const template = props.resources.templates.find(({ id }) => id === ids.templateId)?.name || "未选模板";
  const base = props.resources.base_models.find(({ id }) => id === ids.baseModelId)?.name || "未选BaseModel";
  return `${datasetSummary(row)} · ${template} · ${base}`;
}
function datasetSummary(row: TrainingModelDraft) {
  const ids = effectiveResourceIds(row, props.defaults);
  if (ids.datasetMode === "multi") {
    const config = ids.multiDatasetConfig;
    const selected = props.resources.datasets.filter((item) =>
      config?.dataset_export_ids.includes(item.id),
    );
    const images = selected.reduce((sum, item) => sum + item.total_frames, 0);
    return `${selected.length} 个数据集 · ${config?.target_classes.length ?? 0} 个目标类别 · ${images.toLocaleString()} 张图像`;
  }
  return props.resources.datasets.find(({ id }) => id === ids.datasetId)?.name || "未选数据集";
}
function setDatasetMode(row: TrainingModelDraft, mode: TrainingModelDraft["dataset_mode"]) {
  row.dataset_mode = mode;
  update();
  if (mode === "multi" && !row.multi_dataset_config) emit("configureMapping", row);
}
</script>

<template>
  <div class="model-editor-columns">
    <div v-for="(column, columnIndex) in columns" :key="columnIndex" class="model-editor-column">
      <article v-for="({ row, index }) in column" :key="keyFor(row)" class="model-editor-card">
        <header>
          <button class="card-summary" type="button" :aria-expanded="!collapsed.includes(row)" @click="toggle(row)">
            <span>MODEL {{ String(index + 1).padStart(2, "0") }}</span>
            <strong>{{ row.name || `模型 ${index + 1}` }}</strong>
            <small>GPU {{ row.gpu_index }} / q{{ String(row.queue_order).padStart(2, "0") }} · {{ summary(row) }}</small>
          </button>
          <div class="card-actions">
            <VButton v-if="mode === 'single_device_serial'" variant="quiet" icon-only label="上移" title="上移" :disabled="index === 0" @click="move(index, -1)">
              <template #icon><el-icon><Top /></el-icon></template>
            </VButton>
            <VButton v-if="mode === 'single_device_serial'" variant="quiet" icon-only label="下移" title="下移" :disabled="index === models.length - 1" @click="move(index, 1)">
              <template #icon><el-icon><Bottom /></el-icon></template>
            </VButton>
            <VButton variant="danger" icon-only label="删除模型行" title="删除模型行" :disabled="models.length === 1" @click="remove(index)">
              <template #icon><el-icon><Delete /></el-icon></template>
            </VButton>
            <VButton variant="quiet" icon-only :label="collapsed.includes(row) ? '展开配置' : '收起配置'" :title="collapsed.includes(row) ? '展开配置' : '收起配置'" @click="toggle(row)">
              <template #icon><el-icon><ArrowDown v-if="collapsed.includes(row)" /><ArrowUp v-else /></el-icon></template>
            </VButton>
          </div>
        </header>
        <el-form v-show="!collapsed.includes(row)" label-position="top">
          <div class="form-grid two">
            <el-form-item label="模型名称"><el-input v-model="row.name" maxlength="128" @change="update" /></el-form-item>
            <el-form-item label="GPU / 序号"><div class="inline"><el-select v-model="row.gpu_index" @change="normalize();update()"><el-option v-for="gpu in devices" :key="gpu.index" :value="gpu.index" :label="`GPU ${gpu.index} · 显存 ${gpu.memory_percent}%`" /></el-select><el-input-number v-model="row.queue_order" :min="1" :max="10" :disabled="mode !== 'custom_sequence'" @change="update" /></div></el-form-item>
          </div>
          <el-form-item label="模型描述"><el-input v-model="row.description" type="textarea" :rows="2" maxlength="2000" /></el-form-item>
          <section class="dataset-resource">
            <header><div><strong>训练数据集</strong><small>{{ datasetSummary(row) }}</small></div><VButton size="sm" :disabled="row.dataset_mode !== 'multi'" @click="emit('configureMapping', row)">{{ row.multi_dataset_config ? '配置映射' : '开始配置' }}</VButton></header>
            <el-segmented :model-value="row.dataset_mode" :options="[{ label: '继承任务默认', value: 'inherit' }, { label: '自定义单数据集', value: 'single' }, { label: '自定义多数据集', value: 'multi' }]" @change="setDatasetMode(row, $event as TrainingModelDraft['dataset_mode'])" />
            <el-cascader v-if="row.dataset_mode === 'single'" v-model="row.dataset_export_id" :options="datasetOptions" :props="cascaderProps" filterable clearable placeholder="数据集项目 / 导出数据集" @change="update" />
            <div v-else-if="row.dataset_mode === 'multi' && !row.multi_dataset_config" class="dataset-warning">尚未配置模型多数据集映射；可从任务默认配置复制后编辑。</div>
            <VButton v-if="row.dataset_mode !== 'inherit'" variant="quiet" size="sm" @click="row.dataset_mode = 'inherit'; row.dataset_export_id = null; row.multi_dataset_config = null; update()">恢复任务默认</VButton>
          </section>
          <div class="form-grid resources-grid">
            <el-form-item label="超参模板"><el-select v-model="row.template_id" filterable clearable :placeholder="defaults.default_template_id ? '继承任务默认' : '请选择超参模板'" @change="update"><el-option v-for="item in resources.templates" :key="item.id" :value="item.id" :label="item.name" /></el-select></el-form-item>
            <el-form-item label="Base model"><el-cascader v-model="row.base_model_id" :options="baseModelOptions" :props="cascaderProps" filterable clearable :placeholder="defaults.default_base_model_id ? '继承任务默认' : '请选择 BaseModel'" @change="update" /></el-form-item>
          </div>
          <section class="override-panel">
            <header><div><strong>核心参数覆盖</strong><small>关闭时使用当前有效超参模板</small></div><el-switch :model-value="overrideEnabled(row)" :disabled="!templateFor(row)" @change="setOverride(row, Boolean($event))" /></header>
            <div v-if="overrideEnabled(row)" class="core-grid">
              <el-form-item label="epochs"><el-input-number v-model="row.epochs_override" :min="1" :max="100000" :controls="false" @change="update" /></el-form-item>
              <el-form-item :label="`image size · ${row.image_size_override}`"><el-slider :model-value="row.image_size_override || 32" :min="32" :max="1280" :step="32" @update:model-value="row.image_size_override = Number($event)" @change="update" /></el-form-item>
              <el-form-item label="batch size"><div class="batch-controls"><el-select :model-value="row.batch_mode_override" @change="setBatchMode(row, $event)"><el-option label="自动" value="auto"/><el-option label="固定数量" value="fixed"/><el-option label="显存比例" value="fraction"/></el-select><el-input-number v-model="row.batch_value_override" :class="{ invisible: row.batch_mode_override === 'auto' }" :disabled="row.batch_mode_override === 'auto'" :min="row.batch_mode_override === 'fixed' ? 1 : 0.01" :max="row.batch_mode_override === 'fixed' ? 4096 : 1" :step="row.batch_mode_override === 'fixed' ? 1 : 0.05" :precision="row.batch_mode_override === 'fraction' ? 2 : 0" @change="update" /></div></el-form-item>
            </div>
            <p v-else class="inherited-core">{{ templateFor(row) ? `epochs ${templateFor(row)?.epochs} · image ${templateFor(row)?.image_size} · batch ${templateFor(row)?.batch_mode === 'auto' ? 'auto' : templateFor(row)?.batch_value}` : '选择超参模板后可覆盖核心参数' }}</p>
          </section>
          <p class="artifact-preview"><span>ARTIFACT</span><code>{{ artifactPreview(row, defaults, resources, taskCode) || '选择有效超参模板和 BaseModel 后生成' }}</code></p>
        </el-form>
      </article>
    </div>
  </div>
</template>

<style scoped>
.model-editor-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}.model-editor-column{display:grid;gap:16px}.model-editor-card{min-width:0;border:1px solid var(--vdw-line);background:#fff}.model-editor-card>header{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 14px;background:var(--vdw-surface-2);border-bottom:1px solid var(--vdw-line)}.card-summary{display:flex;min-width:0;flex:1;flex-direction:column;align-items:flex-start;gap:3px;padding:0;border:0;background:transparent;text-align:left;cursor:pointer}.card-summary span,.artifact-preview span{color:var(--vdw-accent);font:14px ui-monospace,monospace;letter-spacing:.08em}.card-summary strong,.card-summary small{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.card-summary small{color:var(--vdw-ink-2);font-size:14px}.card-actions{display:flex;gap:6px}.model-editor-card form{padding:16px}.form-grid{display:grid;gap:12px}.form-grid.two{grid-template-columns:1fr 1fr}.resources-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.inline{display:grid;grid-template-columns:minmax(0,1fr) 96px;gap:8px;width:100%;min-width:0}.inline :deep(.el-select),.inline :deep(.el-input-number){width:100%;min-width:0}.dataset-resource{display:grid;gap:10px;margin-bottom:12px;padding:12px;border:1px solid var(--vdw-line);background:var(--vdw-surface-2)}.dataset-resource>header{display:flex;align-items:center;justify-content:space-between;gap:12px}.dataset-resource>header>div{display:grid;min-width:0}.dataset-resource small{overflow:hidden;color:var(--vdw-ink-2);font-size:14px;text-overflow:ellipsis;white-space:nowrap}.dataset-resource :deep(.el-segmented){justify-self:start}.dataset-warning{padding:8px 10px;border:1px solid var(--vdw-warn-line);background:var(--vdw-warn-soft);color:var(--vdw-warn);font-size:14px}.override-panel{margin-top:2px;padding:12px;background:var(--vdw-app)}.override-panel>header{display:flex;align-items:center;justify-content:space-between}.override-panel>header div{display:flex;flex-direction:column}.override-panel small,.inherited-core{color:var(--vdw-ink-2);font-size:14px}.core-grid{display:grid;grid-template-columns:1fr 1.5fr;gap:0 14px;margin-top:10px}.core-grid>:last-child{grid-column:1/-1}.batch-controls{display:grid;grid-template-columns:1fr 1fr;gap:10px}.invisible{visibility:hidden;pointer-events:none}.inherited-core{margin:10px 0 0}.artifact-preview{display:flex;gap:10px;margin:12px 0 0;padding:9px 11px;overflow:auto;background:var(--vdw-ink);color:var(--vdw-line)}.artifact-preview code{white-space:nowrap}
</style>
