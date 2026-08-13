<script setup lang="ts">
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  checkTrainingTaskCode,
  createTrainingTask,
  getTrainingCapabilities,
  getTrainingResources,
  getTrainingTask,
  startTrainingTask,
  updateTrainingTask,
  type GpuDevice,
  type MultiDatasetConfig,
  type TrainingModelDraft,
  type TrainingResources,
  type TrainingTaskDraft,
} from "../api/training";
import { ApiError } from "../api/auth";
import DatasetSelectionSummary from "../components/DatasetSelectionSummary.vue";
import GpuSequenceEditor from "../components/GpuSequenceEditor.vue";
import TrainingModelEditor from "../components/TrainingModelEditor.vue";
import MultiDatasetMappingDialog from "../components/MultiDatasetMappingDialog.vue";
import PageHeader from "../components/PageHeader.vue";
import { groupedOptions, hasEffectiveResources } from "../components/trainingResources";
import VButton from '../ui/VButton.vue'

const route = useRoute();
const router = useRouter();
const editing = computed(() => Boolean(route.params.id));
const taskVersion = ref(1);
const loading = ref(true);
const saving = ref(false);
const mappingOpen = ref(false);
const mappingModel = ref<TrainingModelDraft | null>(null);
const codeState = ref<"idle" | "checking" | "available" | "conflict" | "failed">("idle");
const codeMessage = ref("");
const devices = ref<GpuDevice[]>([]);
const trainingAvailable = ref(false);
const capabilityReason = ref("");
const resources = ref<TrainingResources>({
  datasets: [],
  templates: [],
  base_models: [],
});
const form = reactive<TrainingTaskDraft>({
  code: "",
  name: "",
  description: "",
  mode: "single_model",
  default_dataset_export_id: null,
  default_dataset_mode: "single",
  default_multi_dataset_config: null,
  default_template_id: null,
  default_base_model_id: null,
  models: [],
});
function row(index: number): TrainingModelDraft {
  return {
    name: `模型 ${index}`,
    description: "",
    dataset_export_id: null,
    dataset_mode: "inherit",
    multi_dataset_config: null,
    template_id: null,
    base_model_id: null,
    epochs_override: null,
    batch_mode_override: null,
    batch_value_override: null,
    image_size_override: null,
    gpu_index: devices.value[0]?.index ?? 0,
    queue_order: index,
  };
}
function add() {
  if (canAdd.value) form.models.push(row(form.models.length + 1));
}
function applyMode(mode: string) {
  if (mode === "single_model" && form.models.length > 1) {
    ElMessageBox.confirm(
      "切换到单模型会只保留第一行模型配置。",
      "切换训练模式",
      { type: "warning" },
    )
      .then(() => {
        form.models.splice(1);
        form.models[0].queue_order = 1;
      })
      .catch(() => {
        form.mode = "single_device_serial";
      });
  } else if (mode === "single_device_serial") {
    const gpu = form.models[0]?.gpu_index ?? devices.value[0]?.index ?? 0;
    form.models.forEach((item, index) => {
      item.gpu_index = gpu;
      item.queue_order = index + 1;
    });
  }
}
watch(() => form.mode, applyMode);
watch(
  () => form.default_dataset_mode,
  (mode) => {
    if (mode === "multi" && !form.default_multi_dataset_config) openTaskMapping();
  },
);
watch(mappingOpen, (open) => {
  if (open) return;
  if (mappingModel.value?.dataset_mode === "multi" && !mappingModel.value.multi_dataset_config)
    mappingModel.value.dataset_mode = "single";
  if (!mappingModel.value && form.default_dataset_mode === "multi" && !form.default_multi_dataset_config)
    form.default_dataset_mode = "single";
});
async function load() {
  try {
    const [available, options] = await Promise.all([
      getTrainingCapabilities(),
      getTrainingResources(),
    ]);
    devices.value = available.devices;
    trainingAvailable.value = available.training_available;
    capabilityReason.value = available.training_reason || "";
    resources.value = options;
    if (editing.value) {
      const task = await getTrainingTask(String(route.params.id));
      Object.assign(form, {
        code: task.code,
        name: task.name,
        description: task.description,
        mode: task.mode,
        default_dataset_export_id: task.default_dataset_export_id,
        default_dataset_mode: task.default_dataset_mode,
        default_multi_dataset_config: task.default_multi_dataset_config,
        default_template_id: task.default_template_id,
        default_base_model_id: task.default_base_model_id,
        models: (task.models || []).map((item) => ({
          name: item.name,
          description: item.description,
          dataset_export_id: item.dataset_export_id,
          dataset_mode: item.dataset_mode,
          multi_dataset_config: item.multi_dataset_config,
          template_id: item.template_id,
          base_model_id: item.base_model_id,
          epochs_override: item.epochs_override,
          batch_mode_override: item.batch_mode_override,
          batch_value_override: item.batch_value_override,
          image_size_override: item.image_size_override,
          gpu_index: item.gpu_index,
          queue_order: item.queue_order,
        })),
      });
      taskVersion.value = task.version;
    } else form.models.push(row(1));
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "训练表单加载失败");
  } finally {
    loading.value = false;
  }
}
const modelsHaveResources = computed(() =>
  form.models.every((item) => hasEffectiveResources(item, form)),
);
const canAdd = computed(() =>
  form.models.length < 10 && form.mode !== "single_model" && modelsHaveResources.value,
);
const datasetOptions = computed(() => groupedOptions(resources.value.datasets));
const baseModelOptions = computed(() => groupedOptions(resources.value.base_models));
const cascaderProps = { emitPath: false };
const valid = computed(
  () =>
    /^[a-z][a-z0-9-]{2,31}$/.test(form.code) &&
    codeState.value !== "conflict" &&
    form.name.trim() &&
    form.models.length >= 1 &&
    form.models.length <= 10 &&
    modelsHaveResources.value &&
    form.models.every((item) => item.name.trim()),
);
function initialMapping(datasetId: string | null): MultiDatasetConfig | null {
  const dataset = resources.value.datasets.find((item) => item.id === datasetId);
  return dataset
    ? { version: 1, dataset_export_ids: [dataset.id], target_classes: dataset.labels.map((item) => item.name) }
    : null;
}
const activeMappingConfig = computed(() => {
  if (!mappingModel.value)
    return form.default_multi_dataset_config ?? initialMapping(form.default_dataset_export_id);
  return mappingModel.value.multi_dataset_config
    ?? form.default_multi_dataset_config
    ?? initialMapping(mappingModel.value.dataset_export_id ?? form.default_dataset_export_id);
});
function openTaskMapping() {
  mappingModel.value = null;
  mappingOpen.value = true;
}
function openModelMapping(model: TrainingModelDraft) {
  mappingModel.value = model;
  mappingOpen.value = true;
}
function saveMapping(config: MultiDatasetConfig) {
  if (mappingModel.value) {
    mappingModel.value.dataset_mode = "multi";
    mappingModel.value.multi_dataset_config = config;
  } else {
    form.default_dataset_mode = "multi";
    form.default_multi_dataset_config = config;
  }
}
async function checkCode() {
  if (editing.value || !/^[a-z][a-z0-9-]{2,31}$/.test(form.code)) {
    codeState.value = "idle";
    codeMessage.value = "";
    return;
  }
  codeState.value = "checking";
  codeMessage.value = "正在检查编码…";
  try {
    const result = await checkTrainingTaskCode(form.code);
    codeState.value = result.available ? "available" : "conflict";
    codeMessage.value = result.available ? "编码可用" : result.reason || "编码已存在";
  } catch {
    codeState.value = "failed";
    codeMessage.value = "暂时无法检查，保存时会再次校验";
  }
}
async function save(start: boolean) {
  if (!valid.value || saving.value) return;
  saving.value = true;
  let saved = false;
  try {
    let task;
    if (editing.value)
      task = await updateTrainingTask(
        String(route.params.id),
        taskVersion.value,
        {
          name: form.name,
          description: form.description,
          mode: form.mode,
          default_dataset_export_id: form.default_dataset_export_id,
          default_dataset_mode: form.default_dataset_mode,
          default_multi_dataset_config: form.default_multi_dataset_config,
          default_template_id: form.default_template_id,
          default_base_model_id: form.default_base_model_id,
          models: form.models,
        },
      );
    else task = await createTrainingTask({ ...form, models: form.models });
    taskVersion.value = task.version;
    saved = true;
    if (start) {
      if (!trainingAvailable.value)
        throw new Error(capabilityReason.value || "当前主机训练能力不可用");
      task = await startTrainingTask(task.id);
    }
    ElMessage.success(start ? "训练任务已提交" : "草稿已保存");
    await router.push(`/training-tasks/${task.id}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 409)
      ElMessage.error("草稿已被其他操作更新，请刷新页面后再保存。");
    else if (saved && start)
      ElMessage.error(`草稿已保存，但启动失败：${e instanceof Error ? e.message : "未知错误"}`);
    else ElMessage.error(e instanceof Error ? e.message : "保存失败");
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>
<template>
  <main v-loading="loading" class="content-page training-editor-page">
    <PageHeader :title="editing ? '编辑训练草稿' : '新建训练任务'" back-to="/training-tasks" back-label="返回训练任务">
      <template #meta><span>仅 YOLO Detect 轴对齐矩形框模型</span></template>
      <template #actions><div>
        <VButton variant="default" @click="router.push('/training-tasks')">取消</VButton
        ><VButton variant="default" :loading="saving" :disabled="!valid || saving" @click="save(false)">保存草稿</VButton
        ><VButton variant="primary" :loading="saving"
          :disabled="!valid || !trainingAvailable || saving"
          @click="save(true)">保存并启动</VButton
        >
      </div></template>
    </PageHeader>
    <div class="content-body">
      <el-alert
        v-if="!trainingAvailable"
        :title="
          capabilityReason || '当前主机不可启动训练，可继续保存草稿和查看历史。'
        "
        type="warning"
        :closable="false"
        show-icon
      />
      <section class="editor-section">
        <header>
          <span>01 / TASK</span>
          <h2>任务基础设置</h2>
        </header>
        <el-form label-position="top"
          ><div class="form-grid two">
            <el-form-item label="训练任务名称"
              ><el-input v-model="form.name" maxlength="128" /></el-form-item
            ><el-form-item label="任务 code"
              ><el-input
                v-model="form.code"
                :disabled="editing"
                placeholder="如 firedet"
                @blur="checkCode"
              />
              <p v-if="codeMessage" class="field-note code-state" :class="codeState">
                {{ codeMessage }}
              </p>
              <p v-else class="field-note">
                3–32 位小写字母、数字或连字符；创建后不可修改且删除后不复用。
              </p></el-form-item>
          </div>
          <el-form-item label="训练描述"
            ><el-input
              v-model="form.description"
              type="textarea"
              :rows="2"
              maxlength="2000" /></el-form-item
        ></el-form>
      </section>
      <section class="editor-section">
        <header>
          <span>02 / DEFAULTS</span>
          <h2>任务总体设置</h2>
        </header>
        <div class="resource-rows">
          <div class="resource-row">
            <div><b>默认数据集</b><span>继承模型共用；单数据集与多数据集配置互相保留</span></div>
            <div class="dataset-default-control">
              <el-segmented v-model="form.default_dataset_mode" :options="[{ label: '单数据集', value: 'single' }, { label: '多数据集', value: 'multi' }]" />
              <el-cascader v-if="form.default_dataset_mode === 'single'" v-model="form.default_dataset_export_id" :options="datasetOptions" :props="cascaderProps" filterable clearable placeholder="未选择任何数据集" />
              <DatasetSelectionSummary
                :mode="form.default_dataset_mode"
                :dataset-id="form.default_dataset_export_id"
                :config="form.default_multi_dataset_config"
                :datasets="resources.datasets"
                @configure-mapping="openTaskMapping"
              />
            </div>
          </div>
          <div class="resource-row"><div><b>默认超参模板</b><span>训练器基础参数</span></div><el-form-item
            ><el-select v-model="form.default_template_id" filterable clearable
              ><el-option
                v-for="item in resources.templates"
                :key="item.id"
                :label="item.name"
                :value="item.id" /></el-select></el-form-item></div
          ><div class="resource-row"><div><b>默认 Base model</b><span>模型初始化权重</span></div><el-form-item>
          <el-cascader
              v-model="form.default_base_model_id"
              :options="baseModelOptions"
              :props="cascaderProps"
              filterable
              clearable
              placeholder="模型项目 / BaseModel"
            />
          </el-form-item></div>
        </div>
        <p class="field-note">
          未设置默认资源时，每个模型行必须单独选择；模型行选择值会覆盖任务默认。
        </p>
      </section>
      <section class="editor-section">
        <header class="model-section-title">
          <div>
            <span>03 / MODELS</span>
            <h2>训练模型与执行顺序</h2>
          </div>
          <VButton variant="default" :disabled="!canAdd"
            :title="modelsHaveResources ? '添加模型' : '请先补齐现有模型的数据集、超参模板和 BaseModel'"
            @click="add">添加模型</VButton
          >
        </header>
        <el-form label-position="top" class="training-mode-field">
          <el-form-item label="训练模式">
            <el-segmented v-model="form.mode" :options="[{ label: '单模型', value: 'single_model' }, { label: '单算力串行', value: 'single_device_serial' }, { label: '自定义序列', value: 'custom_sequence' }]" />
            <p class="field-note">准备训练数据始终在申请 GPU 前完成。</p>
          </el-form-item>
        </el-form>
        <TrainingModelEditor
          :models="form.models"
          :resources="resources"
          :devices="devices"
          :mode="form.mode"
          :task-code="form.code"
          :defaults="form"
          @configure-mapping="openModelMapping"
          @change="form.models = $event"
        /><GpuSequenceEditor
          v-if="form.mode === 'custom_sequence'"
          class="lane-preview"
          :models="form.models"
          :devices="devices"
          @change="form.models = $event"
        />
      </section>
    </div>
    <MultiDatasetMappingDialog v-model="mappingOpen" :config="activeMappingConfig" :datasets="resources.datasets" :title="mappingModel ? `${mappingModel.name || '训练模型'} · 多数据集映射` : '任务默认 · 多数据集映射'" @save="saveMapping" />
  </main>
</template>
<style scoped>
.training-editor-page {
  background: var(--vdw-app);
}
.editor-section {
  margin: 20px 0;
  padding: 24px;
  background: #fff;
  border: 1px solid var(--vdw-line);
}
.editor-section > header {
  margin-bottom: 20px;
}
.editor-section > header span {
  color: var(--vdw-accent);
  font:
    13px ui-monospace,
    monospace;
  letter-spacing: 0.08em;
}
.editor-section h2 {
  margin: 6px 0 0;
  font-size: 19px;
}
.form-grid {
  display: grid;
  gap: 16px;
}
.form-grid.two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.field-note {
  margin: 5px 0 0;
  color: var(--vdw-ink-2);
  font-size: 14px;
}
.model-section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.resource-rows { display: grid; }
.resource-row { display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: 18px; align-items: start; padding: 16px 0; border-bottom: 1px solid var(--vdw-line); }
.resource-row:first-child { padding-top: 0; }
.resource-row:last-child { padding-bottom: 0; border-bottom: 0; }
.resource-row>div:first-child { display: grid; }
.resource-row>div:first-child span { color: var(--vdw-ink-2); font-size: 14px; }
.resource-row :deep(.el-form-item) { margin: 0; }
.resource-row :deep(.el-select),.resource-row :deep(.el-cascader) { width: 100%; }
.dataset-default-control { display: grid; gap: 10px; }
.dataset-default-control :deep(.el-segmented) { justify-self: start; }
.training-mode-field { margin-bottom: 16px; padding: 14px 16px; border: 1px solid var(--vdw-line); background: var(--vdw-surface-2); }
.training-mode-field :deep(.el-form-item) { margin: 0; }
.code-state.available { color: var(--vdw-ok); }
.code-state.conflict,.code-state.failed { color: var(--vdw-danger); }
.code-state.checking { color: var(--vdw-accent-ink); }
.lane-preview {
  margin-top: 18px;
}
</style>
