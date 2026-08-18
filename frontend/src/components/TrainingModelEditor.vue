<script setup lang="ts">
import { ArrowDown, ArrowUp, Bottom, Delete, Top } from "@element-plus/icons-vue";
import { computed, ref } from "vue";
import type { GpuDevice, TrainingModelDraft, TrainingResources } from "../api/training";
import DatasetSelectionSummary from "./DatasetSelectionSummary.vue";
import CoreHyperparameterFields from "./CoreHyperparameterFields.vue";
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
  hyperMessages?: Map<TrainingModelDraft, string>;
}>();
const emit = defineEmits<{
  change: [TrainingModelDraft[]];
  configureMapping: [TrainingModelDraft];
  editHyperparameters: [TrainingModelDraft];
  changeTemplate: [TrainingModelDraft, string | null];
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
function explicitTemplateFor(row: TrainingModelDraft) {
  return props.resources.templates.find((item) => item.id === row.template_id);
}
function overrideEnabled(row: TrainingModelDraft) {
  return row.epochs_override != null
    || row.batch_mode_override != null
    || row.image_size_override != null;
}
function setOverride(row: TrainingModelDraft, enabled: boolean) {
  if (!enabled) {
    row.epochs_override = null;
    row.batch_mode_override = null;
    row.batch_value_override = null;
    row.image_size_override = null;
  } else {
    const template = explicitTemplateFor(row);
    if (!template) return;
    row.epochs_override = template.epochs;
    row.batch_mode_override = template.batch_mode;
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
function setCoreValue(
  row: TrainingModelDraft,
  key: "epochs_override" | "image_size_override",
  value: number,
) {
  row[key] = value;
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
          <button class="card-summary" type="button" :aria-expanded="!collapsed.includes(row)" :aria-controls="`${keyFor(row)}-details`" @click="toggle(row)">
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
        <Transition name="model-details">
        <el-form :id="`${keyFor(row)}-details`" v-show="!collapsed.includes(row)" label-position="top">
          <div class="form-grid two">
            <el-form-item label="模型名称"><el-input v-model="row.name" maxlength="128" @change="update" /></el-form-item>
            <el-form-item label="GPU / 序号"><div class="inline"><el-select v-model="row.gpu_index" @change="normalize();update()"><el-option v-for="gpu in devices" :key="gpu.index" :value="gpu.index" :label="`GPU ${gpu.index} · 显存 ${gpu.memory_percent}%`" /></el-select><el-input-number v-model="row.queue_order" :min="1" :max="10" :disabled="mode !== 'custom_sequence'" @change="update" /></div></el-form-item>
          </div>
          <el-form-item label="模型描述"><el-input v-model="row.description" type="textarea" :rows="2" maxlength="2000" /></el-form-item>
          <section class="dataset-resource">
            <header><div><strong>训练数据集</strong><small>{{ datasetSummary(row) }}</small></div></header>
            <el-segmented :model-value="row.dataset_mode" :options="[{ label: '继承任务默认', value: 'inherit' }, { label: '单数据集', value: 'single' }, { label: '多数据集', value: 'multi' }]" @change="setDatasetMode(row, $event as TrainingModelDraft['dataset_mode'])" />
            <template v-if="row.dataset_mode === 'inherit'">
              <DatasetSelectionSummary
                :mode="effectiveResourceIds(row, defaults).datasetMode"
                :dataset-id="effectiveResourceIds(row, defaults).datasetId"
                :config="effectiveResourceIds(row, defaults).multiDatasetConfig"
                :datasets="resources.datasets"
                :allow-configure="false"
              />
            </template>
            <template v-else-if="row.dataset_mode === 'single'">
              <el-cascader v-model="row.dataset_export_id" :options="datasetOptions" :props="cascaderProps" filterable clearable placeholder="未选择任何数据集" @change="update" />
              <DatasetSelectionSummary mode="single" :dataset-id="row.dataset_export_id" :datasets="resources.datasets" />
            </template>
            <DatasetSelectionSummary
              v-else
              mode="multi"
              :config="row.multi_dataset_config"
              :datasets="resources.datasets"
              @configure-mapping="emit('configureMapping', row)"
            />
          </section>
          <div class="form-grid resources-grid">
            <el-form-item label="超参模板"><el-select :model-value="row.template_id" filterable clearable :placeholder="defaults.default_template_id ? '继承任务默认' : '请选择超参模板'" @change="emit('changeTemplate', row, ($event as string) || null)"><el-option v-for="item in resources.templates" :key="item.id" :value="item.id" :label="item.name" /></el-select></el-form-item>
            <el-form-item label="Base model"><el-cascader v-model="row.base_model_id" :options="baseModelOptions" :props="cascaderProps" filterable clearable :placeholder="defaults.default_base_model_id ? '继承任务默认' : '请选择 BaseModel'" @change="update" /></el-form-item>
          </div>
          <section v-if="row.template_id && explicitTemplateFor(row)" class="override-panel">
            <header><div><strong>超参数设置</strong><small>{{ explicitTemplateFor(row)?.name }} · v{{ explicitTemplateFor(row)?.version }}</small></div><el-switch :model-value="overrideEnabled(row)" @change="setOverride(row, Boolean($event))" /></header>
            <CoreHyperparameterFields
              v-if="overrideEnabled(row)"
              compact
              :epochs="row.epochs_override ?? explicitTemplateFor(row)!.epochs"
              :batch-mode="row.batch_mode_override ?? explicitTemplateFor(row)!.batch_mode"
              :batch-value="row.batch_mode_override == null ? explicitTemplateFor(row)!.batch_value : row.batch_value_override"
              :image-size="row.image_size_override ?? explicitTemplateFor(row)!.image_size"
              @update:epochs="setCoreValue(row, 'epochs_override', $event)"
              @update:batch-mode="setBatchMode(row, $event)"
              @update:batch-value="row.batch_value_override = $event; update()"
              @update:image-size="setCoreValue(row, 'image_size_override', $event)"
            />
            <p v-else class="inherited-core">关闭核心覆盖，使用当前模板的核心参数。</p>
            <div class="full-editor-row">
              <span v-if="hyperMessages?.get(row)" class="applied-message">{{ hyperMessages.get(row) }}</span>
              <VButton variant="default" size="sm" @click="emit('editHyperparameters', row)">编辑完整超参数</VButton>
            </div>
          </section>
          <p class="artifact-preview"><span>ARTIFACT</span><code>{{ artifactPreview(row, defaults, resources, taskCode) || '选择有效超参模板和 BaseModel 后生成' }}</code></p>
        </el-form>
        </Transition>
      </article>
    </div>
  </div>
</template>

<style scoped>
.model-editor-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}.model-editor-column{display:grid;gap:16px}.model-editor-card{min-width:0;border:1px solid var(--vdw-line);background:#fff}.model-editor-card>header{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 14px;background:var(--vdw-surface-2);border-bottom:1px solid var(--vdw-line)}.card-summary{display:flex;min-width:0;flex:1;flex-direction:column;align-items:flex-start;gap:3px;margin:-6px 0;padding:6px 8px;border:0;border-radius:var(--vdw-radius-control);background:transparent;text-align:left;cursor:pointer;transition:color var(--vdw-motion-fast) var(--vdw-ease),background-color var(--vdw-motion-fast) var(--vdw-ease),box-shadow var(--vdw-motion-fast) var(--vdw-ease)}.card-summary:hover{background:var(--vdw-accent-soft);box-shadow:inset 3px 0 var(--vdw-accent)}.card-summary:active{background:#cfe6ec;box-shadow:inset 3px 0 var(--vdw-accent-ink)}.card-summary span,.artifact-preview span{color:var(--vdw-accent);font:14px ui-monospace,monospace;letter-spacing:.08em}.card-summary strong,.card-summary small{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.card-summary small{color:var(--vdw-ink-2);font-size:14px}.card-actions{display:flex;gap:6px}.model-editor-card form{padding:16px}.model-details-enter-active,.model-details-leave-active{overflow:hidden;transition:opacity 220ms var(--vdw-ease),transform 220ms var(--vdw-ease)}.model-details-enter-from,.model-details-leave-to{opacity:0;transform:translateY(-6px)}.form-grid{display:grid;gap:12px}.form-grid.two{grid-template-columns:1fr 1fr}.resources-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.inline{display:grid;grid-template-columns:minmax(0,1fr) 96px;gap:8px;width:100%;min-width:0}.inline :deep(.el-select),.inline :deep(.el-input-number){width:100%;min-width:0}.dataset-resource{display:grid;gap:10px;margin-bottom:12px;padding:12px;border:1px solid var(--vdw-line);background:var(--vdw-surface-2)}.dataset-resource>header{display:flex;align-items:center;justify-content:space-between;gap:12px}.dataset-resource>header>div{display:grid;min-width:0}.dataset-resource small{overflow:hidden;color:var(--vdw-ink-2);font-size:14px;text-overflow:ellipsis;white-space:nowrap}.dataset-resource :deep(.el-segmented){justify-self:start}.override-panel{display:grid;gap:12px;margin-top:2px;padding:12px;background:var(--vdw-app)}.override-panel>header{display:flex;align-items:center;justify-content:space-between}.override-panel>header div{display:flex;flex-direction:column}.override-panel small,.inherited-core{color:var(--vdw-ink-2);font-size:14px}.inherited-core{margin:0}.full-editor-row{display:flex;align-items:center;justify-content:flex-end;gap:10px}.applied-message{min-width:0;flex:1;color:var(--vdw-ok);font-size:14px}.artifact-preview{display:flex;gap:10px;margin:12px 0 0;padding:9px 11px;overflow:auto;background:var(--vdw-ink);color:var(--vdw-line)}.artifact-preview code{white-space:nowrap}
@media(prefers-reduced-motion:reduce){.model-details-enter-active,.model-details-leave-active{transition:none}}
</style>
