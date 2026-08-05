<script setup lang="ts">
import { ArrowDown, ArrowUp, Delete } from "@element-plus/icons-vue";
import type {
  GpuDevice,
  TrainingModelDraft,
  TrainingResources,
} from "../api/training";

const props = defineProps<{
  models: TrainingModelDraft[];
  resources: TrainingResources;
  devices: GpuDevice[];
  mode: string;
  taskCode: string;
}>();
const emit = defineEmits<{ change: [TrainingModelDraft[]] }>();
const rowKeys = new WeakMap<object, string>();
let nextRowKey = 1;
function keyFor(row: TrainingModelDraft) {
  let key = rowKeys.get(row);
  if (!key) {
    key = `training-model-row-${nextRowKey}`;
    nextRowKey += 1;
    rowKeys.set(row, key);
  }
  return key;
}
function update() {
  emit("change", [...props.models]);
}
function remove(index: number) {
  if (props.models.length > 1) {
    props.models.splice(index, 1);
    normalize();
    update();
  }
}
function move(index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= props.models.length) return;
  [props.models[index], props.models[target]] = [
    props.models[target],
    props.models[index],
  ];
  normalize();
  update();
}
function normalize() {
  if (props.mode !== "custom_sequence")
    props.models.forEach((row, index) => {
      row.queue_order = index + 1;
      if (props.mode === "single_device_serial")
        row.gpu_index = props.models[0]?.gpu_index ?? 0;
    });
}
function preview(row: TrainingModelDraft) {
  const template = props.resources.templates.find(
    (item) => item.id === row.template_id,
  );
  const base = props.resources.base_models.find(
    (item) => item.id === row.base_model_id,
  );
  const day = new Date().toISOString().slice(2, 10).replaceAll("-", "");
  const epochs = row.epochs_override ?? template?.epochs ?? "?";
  const size = row.image_size_override ?? template?.image_size ?? "?";
  const batch =
    row.batch_mode_override === "auto"
      ? "auto"
      : (row.batch_value_override ?? template?.batch_value ?? "auto");
  return `${props.taskCode || "task"}-${day}-g${row.gpu_index}-q${String(row.queue_order).padStart(2, "0")}-${base?.model_code ?? "base"}-s${size}-b${batch}-e${epochs}`;
}
</script>

<template>
  <div class="model-editor-list">
    <article
      v-for="(row, index) in models"
      :key="keyFor(row)"
      class="model-editor-card"
    >
      <header>
        <div>
          <span>MODEL {{ String(index + 1).padStart(2, "0") }}</span
          ><strong>{{ row.name || `模型 ${index + 1}` }}</strong>
        </div>
        <div>
          <el-button
            v-if="mode === 'single_device_serial'"
            :icon="ArrowUp"
            circle
            title="上移"
            aria-label="上移"
            @click="move(index, -1)"
          /><el-button
            v-if="mode === 'single_device_serial'"
            :icon="ArrowDown"
            circle
            title="下移"
            aria-label="下移"
            @click="move(index, 1)"
          /><el-button
            :icon="Delete"
            circle
            title="删除模型行"
            aria-label="删除模型行"
            :disabled="models.length === 1"
            @click="remove(index)"
          />
        </div>
      </header>
      <el-form label-position="top">
        <div class="form-grid two">
          <el-form-item label="模型名称"
            ><el-input
              v-model="row.name"
              maxlength="128"
              @change="update" /></el-form-item
          ><el-form-item label="GPU / 序号"
            ><div class="inline">
              <el-select
                v-model="row.gpu_index"
                @change="
                  normalize();
                  update();
                "
                ><el-option
                  v-for="gpu in devices"
                  :key="gpu.index"
                  :value="gpu.index"
                  :label="`GPU ${gpu.index} · 显存 ${gpu.memory_percent}%`" /></el-select
              ><el-input-number
                v-model="row.queue_order"
                :min="1"
                :max="10"
                :disabled="mode !== 'custom_sequence'"
                @change="update"
              /></div
          ></el-form-item>
        </div>
        <el-form-item label="模型描述"
          ><el-input
            v-model="row.description"
            type="textarea"
            :rows="2"
            maxlength="2000"
        /></el-form-item>
        <div class="form-grid three">
          <el-form-item label="数据集"
            ><el-select
              v-model="row.dataset_export_id"
              filterable
              clearable
              placeholder="继承任务默认"
              ><el-option
                v-for="item in resources.datasets"
                :key="item.id"
                :value="item.id"
                :label="`${item.project_name} / ${item.name}`" /></el-select></el-form-item
          ><el-form-item label="超参模板"
            ><el-select
              v-model="row.template_id"
              filterable
              clearable
              placeholder="继承任务默认"
              ><el-option
                v-for="item in resources.templates"
                :key="item.id"
                :value="item.id"
                :label="item.name" /></el-select></el-form-item
          ><el-form-item label="Base model"
            ><el-select
              v-model="row.base_model_id"
              filterable
              clearable
              placeholder="继承任务默认"
              ><el-option
                v-for="item in resources.base_models"
                :key="item.id"
                :value="item.id"
                :label="`${item.project_name} / ${item.name}`" /></el-select
          ></el-form-item>
        </div>
        <div class="override-row">
          <span>核心参数覆盖</span
          ><el-input-number
            v-model="row.epochs_override"
            :min="1"
            placeholder="epochs"
          /><el-select
            v-model="row.batch_mode_override"
            clearable
            placeholder="batch 模式"
            ><el-option label="固定" value="fixed" /><el-option
              label="自动"
              value="auto" /><el-option
              label="显存比例"
              value="fraction" /></el-select
          ><el-input-number
            v-model="row.batch_value_override"
            :disabled="
              !row.batch_mode_override || row.batch_mode_override === 'auto'
            "
            placeholder="batch"
          /><el-input-number
            v-model="row.image_size_override"
            :min="32"
            :step="32"
            placeholder="image size"
          />
        </div>
        <p class="artifact-preview">
          <span>ARTIFACT</span><code>{{ preview(row) }}</code>
        </p>
      </el-form>
    </article>
  </div>
</template>

<style scoped>
.model-editor-list {
  display: grid;
  gap: 16px;
}
.model-editor-card {
  border: 1px solid #d8dee6;
  background: #fff;
}
.model-editor-card > header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 13px 18px;
  background: #f8fafc;
  border-bottom: 1px solid #d8dee6;
}
.model-editor-card > header div:first-child {
  display: flex;
  align-items: center;
  gap: 12px;
}
.model-editor-card > header span,
.artifact-preview span {
  color: #16866f;
  font:
    11px ui-monospace,
    monospace;
  letter-spacing: 0.08em;
}
.model-editor-card form {
  padding: 18px;
}
.form-grid {
  display: grid;
  gap: 14px;
}
.form-grid.two {
  grid-template-columns: 1fr 1fr;
}
.form-grid.three {
  grid-template-columns: repeat(3, 1fr);
}
.inline,
.override-row {
  display: flex;
  gap: 9px;
  width: 100%;
}
.override-row {
  align-items: center;
  padding: 12px;
  background: #f4f7fa;
}
.override-row > span {
  white-space: nowrap;
  color: #687482;
  font-size: 12px;
}
.artifact-preview {
  display: flex;
  gap: 12px;
  margin: 14px 0 0;
  padding: 10px 12px;
  background: #17212b;
  color: #dce5ed;
  overflow: auto;
}
.artifact-preview code {
  white-space: nowrap;
}
@media (max-width: 900px) {
  .form-grid.two,
  .form-grid.three {
    grid-template-columns: 1fr;
  }
  .override-row {
    flex-wrap: wrap;
  }
}
</style>
