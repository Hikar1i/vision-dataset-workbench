<script setup lang="ts">
import { Plus } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  createTrainingTask,
  getTrainingCapabilities,
  getTrainingResources,
  getTrainingTask,
  startTrainingTask,
  updateTrainingTask,
  type GpuDevice,
  type TrainingModelDraft,
  type TrainingResources,
  type TrainingTaskDraft,
} from "../api/training";
import GpuSequenceEditor from "../components/GpuSequenceEditor.vue";
import TrainingModelEditor from "../components/TrainingModelEditor.vue";

const route = useRoute();
const router = useRouter();
const editing = computed(() => Boolean(route.params.id));
const taskVersion = ref(1);
const loading = ref(true);
const saving = ref(false);
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
  default_template_id: null,
  default_base_model_id: null,
  models: [],
});
function row(index: number): TrainingModelDraft {
  return {
    name: `模型 ${index}`,
    description: "",
    dataset_export_id: null,
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
  if (form.models.length < 10) form.models.push(row(form.models.length + 1));
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
        default_template_id: task.default_template_id,
        default_base_model_id: task.default_base_model_id,
        models: (task.models || []).map((item) => ({
          name: item.name,
          description: item.description,
          dataset_export_id: item.dataset_export_id,
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
    } else add();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "训练表单加载失败");
  } finally {
    loading.value = false;
  }
}
const valid = computed(
  () =>
    /^[a-z][a-z0-9-]{2,31}$/.test(form.code) &&
    form.name.trim() &&
    form.models.length >= 1 &&
    form.models.length <= 10 &&
    form.models.every(
      (item) =>
        item.name.trim() &&
        (item.dataset_export_id || form.default_dataset_export_id) &&
        (item.template_id || form.default_template_id) &&
        (item.base_model_id || form.default_base_model_id),
    ),
);
async function save(start: boolean) {
  if (!valid.value) return;
  saving.value = true;
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
          default_template_id: form.default_template_id,
          default_base_model_id: form.default_base_model_id,
          models: form.models,
        },
      );
    else task = await createTrainingTask({ ...form, models: form.models });
    if (start) {
      if (!trainingAvailable.value)
        throw new Error(capabilityReason.value || "当前主机训练能力不可用");
      task = await startTrainingTask(task.id);
    }
    ElMessage.success(start ? "训练任务已提交" : "草稿已保存");
    await router.push(`/training-tasks/${task.id}`);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "保存失败");
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>
<template>
  <main v-loading="loading" class="content-page training-editor-page">
    <header class="content-toolbar">
      <div class="content-toolbar-title">
        <h1>{{ editing ? "编辑训练草稿" : "新建训练任务" }}</h1>
        <span>仅 YOLO Detect 轴对齐矩形框模型</span>
      </div>
      <div>
        <el-button @click="router.push('/training-tasks')">取消</el-button
        ><el-button :loading="saving" :disabled="!valid" @click="save(false)"
          >保存草稿</el-button
        ><el-button
          type="primary"
          :loading="saving"
          :disabled="!valid || !trainingAvailable"
          @click="save(true)"
          >保存并启动</el-button
        >
      </div>
    </header>
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
          ><div class="form-grid three">
            <el-form-item label="训练任务名称"
              ><el-input v-model="form.name" maxlength="128" /></el-form-item
            ><el-form-item label="任务 code"
              ><el-input
                v-model="form.code"
                :disabled="editing"
                placeholder="如 firedet"
              />
              <p class="field-note">
                3–32 位小写字母、数字或连字符；创建后不可修改且删除后不复用。
              </p></el-form-item
            ><el-form-item label="训练模式"
              ><el-select v-model="form.mode"
                ><el-option label="单模型" value="single_model" /><el-option
                  label="单算力串行"
                  value="single_device_serial" /><el-option
                  label="自定义序列"
                  value="custom_sequence" /></el-select
            ></el-form-item>
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
          <h2>整批默认资源</h2>
        </header>
        <div class="form-grid three">
          <el-form-item label="默认数据集"
            ><el-select
              v-model="form.default_dataset_export_id"
              filterable
              clearable
              ><el-option
                v-for="item in resources.datasets"
                :key="item.id"
                :label="`${item.project_name} / ${item.name}`"
                :value="item.id" /></el-select></el-form-item
          ><el-form-item label="默认超参模板"
            ><el-select v-model="form.default_template_id" filterable clearable
              ><el-option
                v-for="item in resources.templates"
                :key="item.id"
                :label="item.name"
                :value="item.id" /></el-select></el-form-item
          ><el-form-item label="默认 Base model"
            ><el-select
              v-model="form.default_base_model_id"
              filterable
              clearable
              ><el-option
                v-for="item in resources.base_models"
                :key="item.id"
                :label="`${item.project_name} / ${item.name}`"
                :value="item.id" /></el-select
          ></el-form-item>
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
          <el-button
            :icon="Plus"
            :disabled="form.models.length >= 10 || form.mode === 'single_model'"
            @click="add"
            >添加模型</el-button
          >
        </header>
        <TrainingModelEditor
          :models="form.models"
          :resources="resources"
          :devices="devices"
          :mode="form.mode"
          :task-code="form.code"
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
  </main>
</template>
<style scoped>
.training-editor-page {
  background: #f4f7fa;
}
.editor-section {
  margin: 20px 0;
  padding: 24px;
  background: #fff;
  border: 1px solid #d8dee6;
}
.editor-section > header {
  margin-bottom: 20px;
}
.editor-section > header span {
  color: #16866f;
  font:
    12px ui-monospace,
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
.form-grid.three {
  grid-template-columns: repeat(3, 1fr);
}
.field-note {
  margin: 5px 0 0;
  color: #687482;
  font-size: 12px;
}
.model-section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.lane-preview {
  margin-top: 18px;
}
@media (max-width: 900px) {
  .form-grid.three {
    grid-template-columns: 1fr;
  }
}
</style>
