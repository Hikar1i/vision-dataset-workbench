<script setup lang="ts">
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import PrecisionRecallChart from "../components/PrecisionRecallChart.vue";
import TrainingMetricsChart from "../components/TrainingMetricsChart.vue";
import MetricTrendChart from "../components/MetricTrendChart.vue";
import PageHeader from "../components/PageHeader.vue";
import VBar from "../ui/VBar.vue";
import VButton from "../ui/VButton.vue";
import VChip from "../ui/VChip.vue";
import VPanel from "../ui/VPanel.vue";
import VTag from "../ui/VTag.vue";
import { trainingStatus } from "../ui/status";
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
const summary = computed(() => {
  if (!model.value) return [];
  const value = model.value;
  return [
    { key: "GPU / 顺序", text: `GPU ${value.gpu_index} / q${String(value.queue_order).padStart(2, "0")}` },
    { key: "epoch", text: `${latest.value?.current_epoch || 0} / ${latest.value?.target_epochs || "—"}` },
    { key: "PID", text: String(latest.value?.pid || "—") },
    { key: "创建", text: formatTime(value.created_at) },
    { key: "开始", text: formatTime(value.started_at) },
    { key: "持续", text: duration(value.started_at, value.finished_at) },
    { key: "结束", text: formatTime(value.finished_at) },
  ];
});
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
  <main class="content-page">
    <PageHeader
      :title="model?.name || '训练模型'"
      kind="training model"
      :code="model?.artifact_code || undefined"
      :back-to="`/training-tasks/${route.params.id}`"
      back-label="返回训练任务"
    >
      <template v-if="model" #meta>
        <span>{{ task?.name }} · GPU {{ model.gpu_index }}</span>
      </template>
      <template v-if="model" #actions>
        <VButton
          :disabled="!model.actions.retry?.allowed"
          :title="model.actions.retry?.message || '重新训练模型'"
          @click="retry"
        >重试</VButton>
        <VButton
          :disabled="!model.actions.resume?.allowed"
          :title="model.actions.resume?.message || '从 last.pt 恢复'"
          @click="resume"
        >恢复中断</VButton>
        <VButton
          :disabled="!model.actions.derive?.allowed"
          :title="model.actions.derive?.message || '派生新训练配置'"
          @click="open('derive')"
        >派生</VButton>
        <VButton
          variant="primary"
          :disabled="!model.actions.extend?.allowed"
          :title="model.actions.extend?.message || '基于 checkpoint 追加训练'"
          @click="open('extend')"
        >追加训练</VButton>
        <VButton
          variant="quiet"
          :disabled="!model.actions.cancel?.allowed"
          :title="model.actions.cancel?.message || '取消当前模型训练'"
          @click="cancel"
        >取消</VButton>
        <VButton
          variant="quiet"
          :disabled="!model.actions.delete?.allowed"
          :title="model.actions.delete?.message || '删除模型任务'"
          @click="remove"
        >删除</VButton>
      </template>
    </PageHeader>

    <div v-if="model" class="content-body detail-body">
      <VPanel>
        <div class="run-hero">
          <div class="run-hero__state">
            <VTag :tone="trainingStatus(model.status).tone">
              {{ trainingStatus(model.status).label }}
            </VTag>
            <b class="vdw-num">{{ model.progress.toFixed(1) }}%</b>
            <VChip>q{{ String(model.queue_order).padStart(2, '0') }}</VChip>
          </div>
          <VBar
            :value="model.progress"
            :tone="trainingStatus(model.status).tone"
            label="模型训练进度"
          />
          <dl class="run-summary">
            <div v-for="item in summary" :key="item.key">
              <dt>{{ item.key }}</dt>
              <dd>{{ item.text }}</dd>
            </div>
          </dl>
        </div>
      </VPanel>

      <el-alert v-if="latest?.error" :title="latest.error" type="error" show-icon :closable="false" />
      <el-alert
        v-if="latest?.warning"
        :title="latest.warning"
        type="warning"
        show-icon
        :closable="false"
      />

      <VPanel title="训练指标">
        <template #head>
          <p class="panel-note">悬浮指针可查看对应 epoch 的横纵轴数值。</p>
        </template>
        <TrainingMetricsChart :metrics="metrics" />
      </VPanel>

      <VPanel title="评估曲线">
        <div class="curves-grid">
          <article class="curve-card">
            <header><strong>PR curve</strong></header>
            <PrecisionRecallChart :curve="prCurve" />
          </article>
          <article class="curve-card">
            <header>
              <strong>mAP50</strong>
              <span class="vdw-num">{{ metrics.at(-1)?.map50?.toFixed(5) ?? '—' }}</span>
            </header>
            <MetricTrendChart
              :metrics="metrics"
              value-key="map50"
              label="mAP50"
              color="#167c55"
              score
            />
          </article>
          <article class="curve-card">
            <header>
              <strong>mAP50:95</strong>
              <span class="vdw-num">{{ metrics.at(-1)?.map50_95?.toFixed(5) ?? '—' }}</span>
            </header>
            <MetricTrendChart
              :metrics="metrics"
              value-key="map50_95"
              label="mAP50:95"
              color="#00738f"
              score
            />
          </article>
        </div>
      </VPanel>

      <VPanel title="训练日志" flush>
        <pre ref="logView" class="run-log">{{ log || '暂无日志输出' }}</pre>
      </VPanel>
    </div>

    <el-dialog
      v-model="dialog"
      :title="dialog === 'derive' ? '派生训练模型' : '追加训练'"
      width="560px"
    >
      <el-form label-position="top">
        <el-form-item label="新任务 code">
          <el-input v-model="action.task_code" placeholder="小写字母、数字或连字符" />
        </el-form-item>
        <el-form-item label="新任务名称">
          <el-input v-model="action.task_name" />
        </el-form-item>
        <template v-if="dialog === 'derive'">
          <el-alert
            title="派生固定使用原数据集与原 basemodel，仅允许修改超参数。"
            type="info"
            show-icon
            :closable="false"
          />
          <div class="inline-fields">
            <el-form-item label="epochs">
              <el-input-number v-model="action.epochs" :min="1" />
            </el-form-item>
            <el-form-item label="image size">
              <el-input-number v-model="action.image_size" :min="32" :step="32" />
            </el-form-item>
          </div>
        </template>
        <template v-else>
          <el-form-item label="追加 epochs">
            <el-input-number v-model="action.additional_epochs" :min="1" />
          </el-form-item>
          <el-form-item label="起点 checkpoint">
            <el-radio-group v-model="action.checkpoint">
              <el-radio value="best">best.pt</el-radio>
              <el-radio value="last">last.pt</el-radio>
            </el-radio-group>
          </el-form-item>
        </template>
        <el-form-item label="GPU 序号">
          <el-input-number v-model="action.gpu_index" :min="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <VButton variant="quiet" @click="dialog = null">取消</VButton>
        <VButton
          variant="primary"
          :disabled="!action.task_code || !action.task_name"
          @click="submitAction"
        >创建草稿</VButton>
      </template>
    </el-dialog>
  </main>
</template>
<style scoped>
.detail-body {
  display: grid;
  align-content: start;
  gap: 14px;
}

.run-hero {
  display: grid;
  gap: 12px;
}

.run-hero__state {
  display: flex;
  align-items: center;
  gap: 11px;
}

.run-hero__state b {
  font-size: 20px;
  font-weight: 500;
}

.run-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 14px;
  margin: 2px 0 0;
  padding-top: 14px;
  border-top: 1px solid var(--vdw-line);
}

.run-summary dt {
  color: var(--vdw-ink-3);
  font-size: 13px;
}

.run-summary dd {
  margin: 5px 0 0;
  font-family: var(--vdw-mono);
  font-size: 14px;
}

.panel-note {
  margin: 0;
  color: var(--vdw-ink-2);
  font-size: 14px;
}

.curves-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.curve-card {
  min-width: 0;
  background: var(--vdw-surface-2);
  border: 1px solid var(--vdw-line);
  border-radius: var(--vdw-radius-card);
}

.curve-card > header {
  display: flex;
  justify-content: space-between;
  padding: 12px 14px 0;
  font-size: 14px;
}

.curve-card > header span {
  color: var(--vdw-ink-3);
  font-size: 13px;
}

/* 日志用深色专注令牌，和标注工作区同一套 */
.run-log {
  max-height: 420px;
  margin: 0;
  padding: 16px;
  overflow: auto;
  color: var(--vdw-focus-ink);
  font: 13px/1.6 var(--vdw-mono);
  white-space: pre-wrap;
  background: var(--vdw-focus-canvas);
  border-radius: 0 0 var(--vdw-radius-card) var(--vdw-radius-card);
}

.inline-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
</style>
