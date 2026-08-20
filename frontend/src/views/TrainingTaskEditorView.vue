<script setup lang="ts">
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
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
import {
  createHyperparameterTemplate,
  getHyperparameterCatalog,
  updateHyperparameterTemplate,
  type HyperparameterConfig,
  type HyperparameterTemplate,
  type ParameterDefinition,
} from "../api/hyperparameters";
import DatasetSelectionSummary from "../components/DatasetSelectionSummary.vue";
import CoreHyperparameterFields from "../components/CoreHyperparameterFields.vue";
import GpuSequenceEditor from "../components/GpuSequenceEditor.vue";
import TrainingModelEditor from "../components/TrainingModelEditor.vue";
import MultiDatasetMappingDialog from "../components/MultiDatasetMappingDialog.vue";
import TrainingHyperparameterDialog from "../components/TrainingHyperparameterDialog.vue";
import PageHeader from "../components/PageHeader.vue";
import {
  applyHyperparameterOverrides,
  diffHyperparameterConfig,
  groupedOptions,
  hyperparameterOverrideCount,
  missingEffectiveResources,
  templateConfig,
  type TrainingHyperparameterOverrides,
} from "../components/trainingResources";
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
const catalog = ref<ParameterDefinition[]>([]);
const hyperOpen = ref(false);
const hyperTarget = ref<"task" | TrainingModelDraft | null>(null);
const hyperConfig = ref<HyperparameterConfig | null>(null);
const taskHyperMessage = ref("");
const modelHyperMessages = ref(new Map<TrainingModelDraft, string>());
const taskCoreEditing = ref(false);
const templateSwitchOpen = ref(false);
let resolveTemplateSwitch: ((choice: "keep" | "clear" | "cancel") => void) | null = null;
const form = reactive<TrainingTaskDraft>({
  code: "",
  name: "",
  description: "",
  mode: "single_model",
  default_dataset_export_id: null,
  default_dataset_mode: "single",
  default_multi_dataset_config: null,
  default_template_id: null,
  default_epochs_override: null,
  default_batch_mode_override: null,
  default_batch_value_override: null,
  default_image_size_override: null,
  default_extra_parameters_override: null,
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
    extra_parameters_override: null,
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
    const [available, options, hyperparameterCatalog] = await Promise.all([
      getTrainingCapabilities(),
      getTrainingResources(),
      getHyperparameterCatalog(),
    ]);
    devices.value = available.devices;
    trainingAvailable.value = available.training_available;
    capabilityReason.value = available.training_reason || "";
    resources.value = options;
    catalog.value = hyperparameterCatalog.items;
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
        default_epochs_override: task.default_epochs_override,
        default_batch_mode_override: task.default_batch_mode_override,
        default_batch_value_override: task.default_batch_value_override,
        default_image_size_override: task.default_image_size_override,
        default_extra_parameters_override: task.default_extra_parameters_override,
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
          extra_parameters_override: item.extra_parameters_override,
          gpu_index: item.gpu_index,
          queue_order: item.queue_order,
        })),
      });
      taskVersion.value = task.version;
      taskCoreEditing.value = task.default_epochs_override != null
        || task.default_batch_mode_override != null
        || task.default_image_size_override != null;
    } else form.models.push(row(1));
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "训练表单加载失败");
  } finally {
    loading.value = false;
  }
}
const modelResourceGaps = computed(() =>
  form.models.map((item) => missingEffectiveResources(item, form, resources.value)),
);
const modelsHaveResources = computed(() =>
  modelResourceGaps.value.every((items) => items.length === 0),
);
const canAdd = computed(() =>
  form.models.length < 10 && form.mode !== "single_model" && !saving.value,
);
const datasetOptions = computed(() => groupedOptions(resources.value.datasets));
const baseModelOptions = computed(() => groupedOptions(resources.value.base_models));
const cascaderProps = { emitPath: false };
const modeModelCountValid = computed(() =>
  form.mode === "single_model"
    ? form.models.length === 1
    : form.mode === "single_device_serial"
      ? form.models.length >= 2
      : form.models.length >= 1,
);
const draftValid = computed(() => Boolean(
    /^[a-z][a-z0-9-]{2,31}$/.test(form.code) &&
    codeState.value !== "conflict" &&
    form.name.trim() &&
    form.models.length <= 10 &&
    modeModelCountValid.value &&
    form.models.every((item) => item.name.trim()),
));
const launchReady = computed(() =>
  draftValid.value && modelsHaveResources.value && trainingAvailable.value,
);
const draftBlockReason = computed(() => {
  if (!form.name.trim()) return "请填写训练任务名称";
  if (!/^[a-z][a-z0-9-]{2,31}$/.test(form.code)) return "请填写合法的任务 code";
  if (codeState.value === "conflict") return codeMessage.value || "任务 code 已存在";
  if (form.models.length > 10) return "训练任务最多包含 10 个模型";
  if (form.mode === "single_model" && form.models.length !== 1) return "单模型模式必须恰好包含一个模型";
  if (form.mode === "single_device_serial" && form.models.length < 2) return "单算力串行模式至少需要两个模型";
  const unnamed = form.models.findIndex((item) => !item.name.trim());
  return unnamed >= 0 ? `请填写模型 ${unnamed + 1} 的名称` : "";
});
const launchBlockReason = computed(() => {
  if (draftBlockReason.value) return draftBlockReason.value;
  const index = modelResourceGaps.value.findIndex((items) => items.length > 0);
  if (index >= 0) {
    const labels = { dataset: "训练数据集", template: "超参模板", baseModel: "BaseModel" };
    return `模型 ${index + 1} 缺少${modelResourceGaps.value[index].map((key) => labels[key]).join("、")}`;
  }
  return trainingAvailable.value ? "" : capabilityReason.value || "当前主机训练能力不可用";
});
const addModelTitle = computed(() => {
  if (saving.value) return "正在保存训练任务";
  if (form.mode === "single_model") return "单模型模式仅允许一个模型";
  return form.models.length >= 10 ? "训练任务最多包含 10 个模型" : "添加模型";
});
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

const taskTemplate = computed(() =>
  resources.value.templates.find((item) => item.id === form.default_template_id) ?? null,
);
const activeHyperTemplate = computed(() => {
  const id = hyperTarget.value === "task"
    ? form.default_template_id
    : hyperTarget.value && hyperTarget.value.template_id;
  return resources.value.templates.find((item) => item.id === id) ?? null;
});

function taskOverrides(): TrainingHyperparameterOverrides {
  return {
    epochs: form.default_epochs_override,
    batchMode: form.default_batch_mode_override,
    batchValue: form.default_batch_value_override,
    imageSize: form.default_image_size_override,
    extra: form.default_extra_parameters_override,
  };
}

function modelOverrides(model: TrainingModelDraft): TrainingHyperparameterOverrides {
  return {
    epochs: model.epochs_override,
    batchMode: model.batch_mode_override,
    batchValue: model.batch_value_override,
    imageSize: model.image_size_override,
    extra: model.extra_parameters_override,
  };
}

function assignTaskOverrides(value: TrainingHyperparameterOverrides) {
  form.default_epochs_override = value.epochs;
  form.default_batch_mode_override = value.batchMode;
  form.default_batch_value_override = value.batchValue;
  form.default_image_size_override = value.imageSize;
  form.default_extra_parameters_override = value.extra;
}

function assignModelOverrides(
  model: TrainingModelDraft,
  value: TrainingHyperparameterOverrides,
) {
  model.epochs_override = value.epochs;
  model.batch_mode_override = value.batchMode;
  model.batch_value_override = value.batchValue;
  model.image_size_override = value.imageSize;
  model.extra_parameters_override = value.extra;
}

function clearTaskCore() {
  form.default_epochs_override = null;
  form.default_batch_mode_override = null;
  form.default_batch_value_override = null;
  form.default_image_size_override = null;
}

function setTaskCoreEditing(enabled: boolean) {
  taskCoreEditing.value = enabled;
  if (!enabled) clearTaskCore();
}

function setTaskBatchMode(mode: TrainingTaskDraft["default_batch_mode_override"]) {
  form.default_batch_mode_override = mode;
  form.default_batch_value_override = mode === "auto" ? null : mode === "fixed" ? 10 : 0.8;
}

async function changeChoice(overrides: TrainingHyperparameterOverrides) {
  if (!hyperparameterOverrideCount(overrides)) return "keep" as const;
  templateSwitchOpen.value = true;
  return new Promise<"keep" | "clear" | "cancel">((resolve) => {
    resolveTemplateSwitch = resolve;
  });
}

function finishTemplateSwitch(choice: "keep" | "clear" | "cancel") {
  templateSwitchOpen.value = false;
  resolveTemplateSwitch?.(choice);
  resolveTemplateSwitch = null;
}

async function changeTaskTemplate(id: string | null) {
  if (id === form.default_template_id) return;
  const choice = await changeChoice(taskOverrides());
  if (choice === "cancel") return;
  if (choice === "clear") {
    assignTaskOverrides({ epochs: null, batchMode: null, batchValue: null, imageSize: null, extra: null });
    taskCoreEditing.value = false;
  }
  form.default_template_id = id;
  taskHyperMessage.value = "";
}

async function changeModelTemplate(model: TrainingModelDraft, id: string | null) {
  if (id === model.template_id) return;
  const choice = await changeChoice(modelOverrides(model));
  if (choice === "cancel") return;
  if (choice === "clear")
    assignModelOverrides(model, { epochs: null, batchMode: null, batchValue: null, imageSize: null, extra: null });
  model.template_id = id;
  const messages = new Map(modelHyperMessages.value);
  messages.delete(model);
  modelHyperMessages.value = messages;
}

function openHyperparameters(target: "task" | TrainingModelDraft) {
  hyperTarget.value = target;
  const template = target === "task"
    ? taskTemplate.value
    : resources.value.templates.find((item) => item.id === target.template_id) ?? null;
  if (!template) return;
  const overrides = target === "task" ? taskOverrides() : modelOverrides(target);
  hyperConfig.value = applyHyperparameterOverrides(templateConfig(template), overrides);
  hyperOpen.value = true;
}

function setHyperMessage(message: string) {
  if (hyperTarget.value === "task") taskHyperMessage.value = message;
  else if (hyperTarget.value) {
    const messages = new Map(modelHyperMessages.value);
    messages.set(hyperTarget.value, message);
    modelHyperMessages.value = messages;
  }
}

function applyHyperparameters(value: HyperparameterConfig) {
  const template = activeHyperTemplate.value;
  if (!template || !hyperTarget.value) return;
  const overrides = diffHyperparameterConfig(templateConfig(template), value);
  if (hyperTarget.value === "task") {
    assignTaskOverrides(overrides);
    taskCoreEditing.value = overrides.epochs != null
      || overrides.batchMode != null
      || overrides.imageSize != null;
  } else assignModelOverrides(hyperTarget.value, overrides);
  const count = hyperparameterOverrideCount(overrides);
  setHyperMessage(`已应用修改：${count} 项覆盖将在保存草稿时生效。`);
  hyperOpen.value = false;
}

function resourceTemplate(item: HyperparameterTemplate): TrainingResources["templates"][number] {
  return {
    id: item.id,
    name: item.name,
    description: item.description,
    epochs: item.epochs,
    batch_mode: item.batch_mode,
    batch_value: item.batch_value,
    image_size: item.image_size,
    extra_parameters: { ...item.extra_parameters },
    effective_parameters: { ...item.effective_parameters },
    version: item.version,
    updated_at: item.updated_at,
    can_edit: item.can_edit,
  };
}

async function saveHyperparameters(value: HyperparameterConfig) {
  const template = activeHyperTemplate.value;
  if (!template || !hyperTarget.value || !template.can_edit) return;
  try {
    const updated = await updateHyperparameterTemplate(template.id, {
      version: template.version,
      name: template.name,
      description: template.description,
      ...value,
    });
    resources.value.templates = resources.value.templates.map((item) =>
      item.id === updated.id ? resourceTemplate(updated) : item,
    );
    if (hyperTarget.value === "task") {
      assignTaskOverrides({ epochs: null, batchMode: null, batchValue: null, imageSize: null, extra: null });
      taskCoreEditing.value = false;
    } else assignModelOverrides(hyperTarget.value, { epochs: null, batchMode: null, batchValue: null, imageSize: null, extra: null });
    setHyperMessage(`已应用修改并保存到模板 v${updated.version}。`);
    hyperOpen.value = false;
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : "模板保存失败");
  }
}

async function deriveHyperparameters(value: HyperparameterConfig) {
  const template = activeHyperTemplate.value;
  if (!template || !hyperTarget.value) return;
  let name: string;
  try {
    const result = await ElMessageBox.prompt("请输入派生模板名称", "应用并派生", {
      inputValue: `${template.name} - 派生`,
      inputValidator: (input) => Boolean(input.trim()) || "请输入模板名称",
      confirmButtonText: "创建并应用",
      cancelButtonText: "取消",
    });
    name = result.value.trim();
  } catch {
    return;
  }
  try {
    const created = await createHyperparameterTemplate({
      name,
      description: template.description,
      ...value,
      derived_from_id: template.id,
    });
    resources.value.templates = [resourceTemplate(created), ...resources.value.templates];
    if (hyperTarget.value === "task") {
      form.default_template_id = created.id;
      assignTaskOverrides({ epochs: null, batchMode: null, batchValue: null, imageSize: null, extra: null });
      taskCoreEditing.value = false;
    } else {
      hyperTarget.value.template_id = created.id;
      assignModelOverrides(hyperTarget.value, { epochs: null, batchMode: null, batchValue: null, imageSize: null, extra: null });
    }
    setHyperMessage(`已应用修改并派生为“${created.name}” v1。`);
    hyperOpen.value = false;
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : "派生模板失败");
  }
}

async function refreshResources() {
  if (loading.value) return;
  try {
    const next = await getTrainingResources();
    const previous = new Map(resources.value.templates.map((item) => [item.id, item]));
    resources.value = next;
    const taskNext = next.templates.find((item) => item.id === form.default_template_id);
    const taskPrevious = form.default_template_id
      ? previous.get(form.default_template_id)
      : undefined;
    if (taskNext && taskPrevious && taskNext.version !== taskPrevious.version)
      taskHyperMessage.value = `模板已更新至 v${taskNext.version}，已保留 ${hyperparameterOverrideCount(taskOverrides())} 项覆盖。`;
    const messages = new Map(modelHyperMessages.value);
    for (const model of form.models) {
      if (!model.template_id) continue;
      const before = previous.get(model.template_id);
      const after = next.templates.find((item) => item.id === model.template_id);
      if (before && after && before.version !== after.version)
        messages.set(model, `模板已更新至 v${after.version}，已保留 ${hyperparameterOverrideCount(modelOverrides(model))} 项覆盖。`);
    }
    modelHyperMessages.value = messages;
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : "超参模板刷新失败");
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
  if ((start ? !launchReady.value : !draftValid.value) || saving.value) return;
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
          default_epochs_override: form.default_epochs_override,
          default_batch_mode_override: form.default_batch_mode_override,
          default_batch_value_override: form.default_batch_value_override,
          default_image_size_override: form.default_image_size_override,
          default_extra_parameters_override: form.default_extra_parameters_override,
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
onMounted(async () => {
  await load();
  window.addEventListener("focus", refreshResources);
});
onUnmounted(() => window.removeEventListener("focus", refreshResources));
</script>
<template>
  <main v-loading="loading" class="content-page training-editor-page">
    <PageHeader :title="editing ? '编辑训练草稿' : '新建训练任务'" back-to="/training-tasks" back-label="返回训练任务">
      <template #meta><span>仅 YOLO Detect 轴对齐矩形框模型</span></template>
      <template #actions><div>
        <VButton variant="default" @click="router.push('/training-tasks')">取消</VButton
        ><VButton variant="default" :loading="saving" :disabled="!draftValid || saving" :title="draftBlockReason" @click="save(false)">保存草稿</VButton
        ><VButton variant="primary" :loading="saving"
          :disabled="!launchReady || saving"
          :title="launchBlockReason"
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
          <div class="resource-row hyperparameter-resource-row">
            <div><b>默认超参模板</b><span>训练器基础参数</span></div>
            <div class="hyperparameter-default-control">
              <el-form-item>
                <el-select
                  :model-value="form.default_template_id"
                  filterable
                  clearable
                  placeholder="请选择超参模板"
                  @change="changeTaskTemplate(($event as string) || null)"
                >
                  <el-option
                    v-for="item in resources.templates"
                    :key="item.id"
                    :label="`${item.name} · v${item.version}`"
                    :value="item.id"
                  />
                </el-select>
              </el-form-item>
              <section v-if="taskTemplate" class="task-override-card">
                <header>
                  <div>
                    <strong>{{ taskTemplate.name }} · v{{ taskTemplate.version }}</strong>
                    <small>
                      epochs {{ taskTemplate.epochs }} · image {{ taskTemplate.image_size }} · batch
                      {{ taskTemplate.batch_mode === "auto" ? "auto" : taskTemplate.batch_value }}
                    </small>
                  </div>
                  <label>
                    <span>核心参数覆盖</span>
                    <el-switch
                      :model-value="taskCoreEditing"
                      @change="setTaskCoreEditing(Boolean($event))"
                    />
                  </label>
                </header>
                <CoreHyperparameterFields
                  v-if="taskCoreEditing"
                  :epochs="form.default_epochs_override ?? taskTemplate.epochs"
                  :batch-mode="form.default_batch_mode_override ?? taskTemplate.batch_mode"
                  :batch-value="form.default_batch_mode_override == null ? taskTemplate.batch_value : form.default_batch_value_override"
                  :image-size="form.default_image_size_override ?? taskTemplate.image_size"
                  @update:epochs="form.default_epochs_override = $event"
                  @update:batch-mode="setTaskBatchMode($event)"
                  @update:batch-value="form.default_batch_value_override = $event"
                  @update:image-size="form.default_image_size_override = $event"
                />
                <div class="full-editor-row">
                  <span v-if="taskHyperMessage" class="applied-message">{{ taskHyperMessage }}</span>
                  <VButton variant="default" @click="openHyperparameters('task')">
                    编辑完整超参数
                  </VButton>
                </div>
              </section>
            </div>
          </div
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
            :title="addModelTitle"
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
          :hyper-messages="modelHyperMessages"
          @configure-mapping="openModelMapping"
          @edit-hyperparameters="openHyperparameters"
          @change-template="changeModelTemplate"
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
    <TrainingHyperparameterDialog
      v-model="hyperOpen"
      :config="hyperConfig"
      :catalog="catalog"
      :template="activeHyperTemplate"
      @apply="applyHyperparameters"
      @save="saveHyperparameters"
      @derive="deriveHyperparameters"
    />
    <el-dialog
      v-model="templateSwitchOpen"
      title="切换超参模板"
      width="560px"
      :show-close="false"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
    >
      <p class="template-switch-message">当前已有超参数覆盖。请选择切换到新模板后的处理方式。</p>
      <template #footer>
        <VButton variant="quiet" @click="finishTemplateSwitch('cancel')">取消</VButton>
        <VButton variant="default" @click="finishTemplateSwitch('clear')">清空覆盖并使用新模板</VButton>
        <VButton variant="primary" @click="finishTemplateSwitch('keep')">保留覆盖并应用到新模板</VButton>
      </template>
    </el-dialog>
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
.hyperparameter-default-control { display: grid; gap: 10px; }
.task-override-card { display: grid; gap: 14px; padding: 16px; border: 1px solid var(--vdw-line); border-radius: var(--vdw-radius-card); background: var(--vdw-surface-2); }
.task-override-card>header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.task-override-card>header>div { display: flex; min-width: 0; flex-direction: column; }
.task-override-card>header small { overflow: hidden; color: var(--vdw-ink-2); font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.task-override-card>header label { display: flex; align-items: center; gap: 9px; white-space: nowrap; }
.full-editor-row { display: flex; align-items: center; justify-content: flex-end; gap: 12px; }
.applied-message { min-width: 0; flex: 1; color: var(--vdw-ok); font-size: 14px; }
.template-switch-message { margin: 0; color: var(--vdw-ink-2); }
.training-mode-field { margin-bottom: 16px; padding: 14px 16px; border: 1px solid var(--vdw-line); background: var(--vdw-surface-2); }
.training-mode-field :deep(.el-form-item) { margin: 0; }
.code-state.available { color: var(--vdw-ok); }
.code-state.conflict,.code-state.failed { color: var(--vdw-danger); }
.code-state.checking { color: var(--vdw-accent-ink); }
.lane-preview {
  margin-top: 18px;
}
</style>
