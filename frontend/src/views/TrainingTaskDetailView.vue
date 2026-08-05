<script setup lang="ts">
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  cancelTrainingTask,
  deleteTrainingTask,
  deriveTrainingTask,
  getTrainingTask,
  retryFailedTrainingModels,
  type TrainingTask,
} from "../api/training";
import {
  forgetResource,
  rememberResource,
} from "../navigation/recentResources";
const route = useRoute();
const router = useRouter();
const task = ref<TrainingTask>();
const error = ref("");
let timer: number | undefined;
const active = computed(
  () =>
    task.value &&
    ["queued", "running", "canceling"].includes(task.value.status),
);
const groups = computed(() => {
  const map = new Map<number, NonNullable<TrainingTask["models"]>>();
  for (const model of task.value?.models || []) {
    const lane = map.get(model.gpu_index) || [];
    lane.push(model);
    map.set(model.gpu_index, lane);
  }
  return [...map.entries()];
});
const labels: Record<string, string> = {
  draft: "草稿",
  queued: "排队中",
  running: "进行中",
  canceling: "取消中",
  canceled: "已取消",
  start_failed: "启动异常",
  failed: "异常结束",
  partial: "部分完成",
  succeeded: "全部完成",
};
async function load() {
  try {
    task.value = await getTrainingTask(String(route.params.id));
    rememberResource("vdm.recent-training-tasks", task.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "训练任务加载失败";
  }
}
async function cancel() {
  try {
    await ElMessageBox.confirm(
      "取消后，排队模型立即取消，运行模型会先终止进程。已生成的 last.pt 将按规则保留。",
      "取消训练任务",
      { type: "warning" },
    );
    task.value = await cancelTrainingTask(String(route.params.id));
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message);
  }
}
async function remove() {
  try {
    await ElMessageBox.confirm(
      "训练任务配置、运行日志和未发布 checkpoint 将移入 .deleted；已发布模型不会删除。",
      "删除训练任务",
      { type: "warning" },
    );
    await deleteTrainingTask(String(route.params.id));
    forgetResource("vdm.recent-training-tasks", String(route.params.id));
    await router.push("/training-tasks");
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message);
  }
}
async function retryFailed() {
  try {
    await ElMessageBox.confirm(
      "只为失败、启动异常或已取消的模型创建新运行；成功模型保持不变。",
      "重试未成功模型",
    );
    task.value = await retryFailedTrainingModels(String(route.params.id));
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message);
  }
}
async function derive() {
  if (!task.value) return;
  try {
    const result = await ElMessageBox.prompt(
      "填写新任务 code。派生任务固定使用每个模型原来的数据集与 basemodel，仅允许后续修改超参数。",
      "派生训练任务",
      {
        inputPattern: /^[a-z][a-z0-9-]{2,31}$/,
        inputErrorMessage: "请输入 3–32 位小写字母、数字或连字符",
      },
    );
    const created = await deriveTrainingTask(task.value.id, {
      task_code: result.value,
      task_name: `${task.value.name} 派生`,
      description: task.value.description,
    });
    await router.push(`/training-tasks/${created.id}/edit`);
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message);
  }
}
onMounted(async () => {
  await load();
  timer = window.setInterval(() => {
    if (active.value) void load();
  }, 1500);
});
onBeforeUnmount(() => clearInterval(timer));
</script>
<template>
  <main class="content-page training-detail-page">
    <header class="content-toolbar">
      <div class="content-toolbar-title">
        <h1>{{ task?.name || "训练任务" }}</h1>
        <span>{{ task?.code }}</span>
      </div>
      <div v-if="task">
        <el-button
          v-if="task.status === 'draft' && task.can_manage"
          @click="router.push(`/training-tasks/${task.id}/edit`)"
          >编辑草稿</el-button
        ><el-button
          v-if="!active && task.status !== 'draft' && task.can_manage"
          @click="derive"
          >派生任务</el-button
        ><el-button
          v-if="
            ['failed', 'partial', 'canceled', 'start_failed'].includes(
              task.status,
            ) && task.can_manage
          "
          @click="retryFailed"
          >重试未成功模型</el-button
        ><el-button
          v-if="active && task.can_manage"
          type="warning"
          @click="cancel"
          >取消任务</el-button
        ><el-button
          v-if="!active && task.can_manage"
          type="danger"
          @click="remove"
          >删除任务</el-button
        >
      </div>
    </header>
    <div class="content-body">
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
      /><template v-if="task"
        ><section class="run-hero">
          <div>
            <span>STATUS</span><strong>{{ labels[task.status] }}</strong>
          </div>
          <div>
            <span>PROGRESS</span
            ><strong>{{ task.progress.toFixed(1) }}%</strong>
          </div>
          <div>
            <span>MODE</span
            ><strong>{{
              task.mode === "single_model"
                ? "单模型"
                : task.mode === "single_device_serial"
                  ? "单算力串行"
                  : "自定义序列"
            }}</strong>
          </div>
          <div>
            <span>LAST RUN</span
            ><strong>{{
              (task.last_run_at || task.created_at)
                .slice(0, 19)
                .replace("T", " ")
            }}</strong>
          </div>
          <el-progress
            :percentage="task.progress"
            :stroke-width="8"
            :show-text="false"
          />
        </section>
        <section
          v-for="[gpu, models] in groups"
          :key="gpu"
          class="lane-section"
        >
          <header>
            <div>
              <span>GPU LANE</span>
              <h2>GPU {{ gpu }}</h2>
            </div>
            <small>{{ models.length }} 个模型 · 同卡严格串行</small>
          </header>
          <article
            v-for="model in models"
            :key="model.id"
            class="model-run-card"
          >
            <div class="order">
              q{{ String(model.queue_order).padStart(2, "0") }}
            </div>
            <div class="identity">
              <strong>{{ model.name }}</strong
              ><code>{{ model.artifact_code || "启动时冻结产物名" }}</code>
            </div>
            <el-tag
              :type="
                model.status === 'succeeded'
                  ? 'success'
                  : model.status === 'failed' || model.status === 'start_failed'
                    ? 'danger'
                    : model.status === 'running'
                      ? 'warning'
                      : 'info'
              "
              >{{ labels[model.status] }}</el-tag
            >
            <div class="model-progress">
              <el-progress
                :percentage="model.progress"
                :show-text="false"
              /><span
                >{{ model.runs[0]?.current_epoch || 0 }} /
                {{ model.runs[0]?.target_epochs || "—" }} epoch</span
              >
            </div>
            <div class="run-meta">
              <span v-if="model.runs[0]?.pid">PID {{ model.runs[0].pid }}</span
              ><span v-if="model.runs[0]?.started_at"
                >{{ model.runs[0].started_at.slice(11, 19) }} 开始</span
              >
            </div>
            <router-link :to="`/training-tasks/${task.id}/models/${model.id}`"
              >训练详情</router-link
            >
          </article>
        </section></template
      >
    </div>
  </main>
</template>
<style scoped>
.training-detail-page {
  background: #f4f7fa;
}
.run-hero {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  margin: 20px 0;
  background: #d8dee6;
  border: 1px solid #d8dee6;
}
.run-hero > div {
  display: grid;
  gap: 8px;
  padding: 20px;
  background: white;
}
.run-hero span,
.lane-section header span {
  color: #16866f;
  font:
    11px ui-monospace,
    monospace;
  letter-spacing: 0.08em;
}
.run-hero .el-progress {
  grid-column: 1/-1;
  padding: 13px;
  background: white;
}
.lane-section {
  margin: 18px 0;
  border: 1px solid #d8dee6;
  background: #fff;
}
.lane-section > header {
  display: flex;
  justify-content: space-between;
  align-items: end;
  padding: 16px 20px;
  background: #17212b;
  color: #fff;
}
.lane-section h2 {
  margin: 4px 0 0;
}
.lane-section small {
  color: #b8c4cd;
}
.model-run-card {
  display: grid;
  grid-template-columns:
    48px minmax(220px, 1.3fr) 92px minmax(170px, 0.7fr)
    120px 80px;
  gap: 14px;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e9ef;
}
.order {
  color: #16866f;
  font:
    600 13px ui-monospace,
    monospace;
}
.identity {
  display: grid;
  gap: 5px;
}
.identity code {
  overflow: hidden;
  color: #687482;
  font-size: 11px;
  text-overflow: ellipsis;
}
.model-progress {
  display: grid;
  gap: 4px;
}
.model-progress span,
.run-meta {
  color: #687482;
  font-size: 11px;
}
.run-meta {
  display: grid;
}
.model-run-card > a {
  color: #2563eb;
  text-decoration: none;
}
@media (max-width: 900px) {
  .run-hero {
    grid-template-columns: 1fr 1fr;
  }
  .model-run-card {
    grid-template-columns: auto 1fr auto;
  }
  .model-progress,
  .run-meta {
    grid-column: 2/-1;
  }
}
</style>
