<script setup lang="ts">
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import PrecisionRecallChart from "../components/PrecisionRecallChart.vue";
import TrainingMetricsChart from "../components/TrainingMetricsChart.vue";
import MetricTrendChart from "../components/MetricTrendChart.vue";
import PageHeader from "../components/PageHeader.vue";
import {
  cancelTrainingModel,
  deleteTrainingModel,
  deriveTrainingModel,
  extendTrainingModel,
  getTrainingLog,
  getTrainingMetrics,
  getTrainingPrCurve,
  getTrainingTask,
  resumeTrainingModel,
  retryTrainingModel,
  type TrainingMetric,
  type PrCurve,
  type TrainingModel,
  type TrainingTask,
} from "../api/training";
const route = useRoute();
const router = useRouter();
const task = ref<TrainingTask>();
const model = ref<TrainingModel>();
const metrics = ref<TrainingMetric[]>([]);
const prCurve = ref<PrCurve>({ version: 1, kind: "unavailable", series: [] });
const log = ref("");
const logView = ref<HTMLElement>();
const dialog = ref<"derive" | "extend" | null>(null);
const action = reactive({
  task_code: "",
  task_name: "",
  epochs: null as number | null,
  batch_mode: null as "auto" | "fixed" | "fraction" | null,
  batch_value: null as number | null,
  image_size: null as number | null,
  additional_epochs: 50,
  checkpoint: "best",
  gpu_index: 0,
});
let timer: number | undefined;
const latest = computed(() => model.value?.runs[0]);
const active = computed(
  () =>
    model.value &&
    ["queued", "running", "canceling"].includes(model.value.status),
);
function formatTime(value: string | null | undefined) {
  return value ? value.slice(0, 19).replace("T", " ") : "—";
}
function duration(start: string | null | undefined, end: string | null | undefined) {
  if (!start) return "—";
  const seconds = Math.max(0, Math.floor(((end ? Date.parse(end) : Date.now()) - Date.parse(start)) / 1000));
  const hours = Math.floor(seconds / 3600);
  return `${hours ? `${hours}h ` : ""}${String(Math.floor(seconds % 3600 / 60)).padStart(2, "0")}m ${String(seconds % 60).padStart(2, "0")}s`;
}
async function load() {
  task.value = await getTrainingTask(String(route.params.id));
  model.value = task.value.models?.find(
    (item) => item.id === route.params.modelId,
  );
  if (!model.value) return;
  const run = model.value.runs[0];
  if (run) {
    metrics.value = await getTrainingMetrics(run.id);
    prCurve.value = await getTrainingPrCurve(run.id);
    log.value = (await getTrainingLog(run.id)).content;
    await nextTick();
    if (logView.value) logView.value.scrollTop = logView.value.scrollHeight;
  }
}
async function cancel() {
  try {
    await ElMessageBox.confirm(
      "只取消这个模型；同一 GPU lane 的后续模型仍会继续。",
      "取消模型训练",
      { type: "warning" },
    );
    await cancelTrainingModel(String(route.params.modelId));
    await load();
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message);
  }
}
async function retry() {
  if (!model.value) return;
  try {
    let confirm = false;
    if (model.value.status === "succeeded") {
      await ElMessageBox.confirm(
        "该模型已经成功发布。重试成功后将原子替换现有发布模型；重试失败时继续保留当前模型。",
        "确认重试成功模型",
        { type: "warning", confirmButtonText: "确认重新训练" },
      );
      confirm = true;
    }
    await retryTrainingModel(model.value.id, confirm);
    await load();
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message);
  }
}
async function remove() {
  if (!model.value) return;
  const published = model.value.status === "succeeded";
  try {
    await ElMessageBox.confirm(
      published
        ? "该模型已经发布。删除会同时逻辑删除模型项目中的发布模型，并将权重和运行目录移入 .deleted。"
        : "删除会将该模型的运行目录移入工作区 .deleted。",
      "删除训练模型",
      { type: "warning", confirmButtonText: "确认删除" },
    );
    await deleteTrainingModel(model.value.id, published);
    await router.push(`/training-tasks/${task.value?.id}`);
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message);
  }
}
async function resume() {
  try {
    await ElMessageBox.confirm(
      "将从上一运行的 last.pt 恢复中断状态，目标 epoch 保持不变。",
      "恢复中断",
    );
    await resumeTrainingModel(String(route.params.modelId));
    await load();
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message);
  }
}
function open(kind: "derive" | "extend") {
  dialog.value = kind;
  action.task_code = "";
  action.task_name = `${model.value?.name || "模型"} ${kind === "derive" ? "派生" : "追加训练"}`;
  action.gpu_index = model.value?.gpu_index || 0;
}
async function submitAction() {
  if (!model.value) return;
  try {
    const created =
      dialog.value === "derive"
        ? await deriveTrainingModel(model.value.id, {
            task_code: action.task_code,
            task_name: action.task_name,
            description: "",
            epochs: action.epochs,
            batch_mode: action.batch_mode,
            batch_value: action.batch_value,
            image_size: action.image_size,
            gpu_index: action.gpu_index,
          })
        : await extendTrainingModel(model.value.id, {
            task_code: action.task_code,
            task_name: action.task_name,
            additional_epochs: action.additional_epochs,
            checkpoint: action.checkpoint,
            gpu_index: action.gpu_index,
          });
    dialog.value = null;
    await router.push(`/training-tasks/${created.id}/edit`);
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "操作失败");
  }
}
onMounted(async () => {
  try {
    await load();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "训练详情加载失败");
  }
  timer = window.setInterval(() => {
    if (active.value) void load();
  }, 1500);
  if (route.query.action === "derive" || route.query.action === "extend") open(route.query.action);
});
onBeforeUnmount(() => clearInterval(timer));
</script>
<template>
  <main class="content-page training-model-page">
    <PageHeader :title="model?.name || '训练模型'" :back-to="`/training-tasks/${route.params.id}`" back-label="返回训练任务">
      <template #meta><span>{{ model?.artifact_code || "未冻结产物名" }}</span></template>
      <template v-if="model" #actions><div>
        <el-button type="warning" :disabled="!model.actions.cancel?.allowed" :title="model.actions.cancel?.message || '取消当前模型训练'" @click="cancel">取消</el-button
        ><el-button :disabled="!model.actions.retry?.allowed" :title="model.actions.retry?.message || '重新训练模型'" @click="retry"
          >重试</el-button
        ><el-button :disabled="!model.actions.resume?.allowed" :title="model.actions.resume?.message || '从 last.pt 恢复'" @click="resume"
          >恢复中断</el-button
        ><el-button :disabled="!model.actions.derive?.allowed" :title="model.actions.derive?.message || '派生新训练配置'" @click="open('derive')"
          >派生</el-button
        ><el-button
          type="primary"
          :disabled="!model.actions.extend?.allowed"
          :title="model.actions.extend?.message || '基于 checkpoint 追加训练'"
          @click="open('extend')"
          >追加训练</el-button
        ><el-button
          type="danger"
          :disabled="!model.actions.delete?.allowed"
          :title="model.actions.delete?.message || '删除模型任务'"
          @click="remove"
          >删除</el-button
        >
      </div></template>
    </PageHeader>
    <div class="content-body" v-if="model">
      <section class="model-summary">
        <div>
          <span>STATUS</span><strong>{{ model.status }}</strong>
        </div>
        <div>
          <span>GPU / ORDER</span
          ><strong
            >GPU {{ model.gpu_index }} / q{{
              String(model.queue_order).padStart(2, "0")
            }}</strong
          >
        </div>
        <div>
          <span>EPOCH</span
          ><strong
            >{{ latest?.current_epoch || 0 }} /
            {{ latest?.target_epochs || "—" }}</strong
          >
        </div>
        <div>
          <span>PID</span><strong>{{ latest?.pid || "—" }}</strong>
        </div>
        <div><span>CREATED</span><strong>{{ formatTime(model.created_at) }}</strong></div>
        <div><span>STARTED</span><strong>{{ formatTime(model.started_at) }}</strong></div>
        <div><span>DURATION</span><strong>{{ duration(model.started_at, model.finished_at) }}</strong></div>
        <div><span>FINISHED</span><strong>{{ formatTime(model.finished_at) }}</strong></div>
      </section>
      <el-alert
        v-if="latest?.error"
        :title="latest.error"
        type="error"
        :closable="false"
      /><el-alert
        v-if="latest?.warning"
        :title="latest.warning"
        type="warning"
        :closable="false"
      />
      <section class="panel">
        <header>
          <span>METRICS</span>
          <h2>训练指标</h2>
          <p>
            每项指标独立展示；悬浮指针可查看对应 epoch 的横纵轴数值。
          </p>
        </header>
        <TrainingMetricsChart :metrics="metrics" />
      </section>
      <section class="panel">
        <header>
          <span>CURVES</span>
          <h2>评估曲线</h2>
        </header>
        <div class="curves-grid">
          <article class="curve-card"><header><strong>PR curve</strong></header><PrecisionRecallChart :curve="prCurve" /></article>
          <article class="curve-card"><header><strong>mAP50</strong><span>{{ metrics.at(-1)?.map50?.toFixed(5) ?? '—' }}</span></header><MetricTrendChart :metrics="metrics" value-key="map50" label="mAP50" color="#4d7c0f" score /></article>
          <article class="curve-card"><header><strong>mAP50:95</strong><span>{{ metrics.at(-1)?.map50_95?.toFixed(5) ?? '—' }}</span></header><MetricTrendChart :metrics="metrics" value-key="map50_95" label="mAP50:95" color="#7c3aed" score /></article>
        </div>
      </section>
      <section class="panel">
        <header>
          <span>RUN LOG</span>
          <h2>训练日志</h2>
        </header>
        <pre ref="logView">{{ log || "暂无日志输出" }}</pre>
      </section>
    </div>
    <el-dialog
      v-model="dialog"
      :title="dialog === 'derive' ? '派生训练模型' : '追加训练'"
      width="520px"
      ><el-form label-position="top"
        ><el-form-item label="新任务 code"
          ><el-input
            v-model="action.task_code"
            placeholder="小写字母、数字或连字符" /></el-form-item
        ><el-form-item label="新任务名称"
          ><el-input v-model="action.task_name" /></el-form-item
        ><template v-if="dialog === 'derive'"
          ><el-alert
            title="派生固定使用原数据集与原 basemodel，仅允许修改超参数。"
            type="info"
            :closable="false" />
          <div class="inline-fields">
            <el-form-item label="epochs"
              ><el-input-number
                v-model="action.epochs"
                :min="1" /></el-form-item
            ><el-form-item label="image size"
              ><el-input-number
                v-model="action.image_size"
                :min="32"
                :step="32"
            /></el-form-item></div></template
        ><template v-else
          ><el-form-item label="追加 epochs"
            ><el-input-number
              v-model="action.additional_epochs"
              :min="1" /></el-form-item
          ><el-form-item label="起点 checkpoint"
            ><el-radio-group v-model="action.checkpoint"
              ><el-radio value="best">best.pt</el-radio
              ><el-radio value="last">last.pt</el-radio></el-radio-group
            ></el-form-item
          ></template
        ><el-form-item label="GPU 序号"
          ><el-input-number
            v-model="action.gpu_index"
            :min="0" /></el-form-item></el-form
      ><template #footer
        ><el-button @click="dialog = null">取消</el-button
        ><el-button
          type="primary"
          :disabled="!action.task_code || !action.task_name"
          @click="submitAction"
          >创建草稿</el-button
        ></template
      ></el-dialog
    >
  </main>
</template>
<style scoped>
.training-model-page {
  background: #f4f7fa;
}
.model-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  margin: 20px 0;
  background: #d8dee6;
  border: 1px solid #d8dee6;
}
.model-summary div {
  display: grid;
  gap: 7px;
  padding: 18px;
  background: #fff;
}
.model-summary span,
.panel > header span {
  color: #16866f;
  font:
    11px ui-monospace,
    monospace;
  letter-spacing: 0.08em;
}
.panel {
  margin: 18px 0;
  padding: 22px;
  background: #fff;
  border: 1px solid #d8dee6;
}
.panel h2 {
  margin: 5px 0;
}
.panel header p {
  margin: 5px 0;
  color: #687482;
  font-size: 13px;
}
.curves-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.curve-card{min-width:0;border:1px solid #e0e5eb;background:#fbfcfd}.curve-card>header{display:flex;justify-content:space-between;padding:12px 14px 0}.curve-card>header span{color:#687482;font:12px ui-monospace,monospace}
.metric-table {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px;
  background: #f4f7fa;
  color: #687482;
  font:
    11px ui-monospace,
    monospace;
}
.pr-panel svg {
  width: min(100%, 650px);
  height: 300px;
}
.pr-panel polyline {
  fill: none;
  stroke: #16866f;
  stroke-width: 3;
}
.pr-panel .guide {
  fill: none;
  stroke: #d8dee6;
  stroke-width: 1;
}
.pr-panel text {
  fill: #687482;
  font-size: 12px;
}
.panel pre {
  max-height: 420px;
  margin: 14px 0 0;
  padding: 16px;
  overflow: auto;
  background: #17212b;
  color: #dce5ed;
  font:
    12px/1.6 ui-monospace,
    monospace;
  white-space: pre-wrap;
}
.inline-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 800px) {
  .model-summary {
    grid-template-columns: 1fr 1fr;
  }
  .curves-grid{grid-template-columns:1fr}
}
</style>
