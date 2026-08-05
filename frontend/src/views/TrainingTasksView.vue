<script setup lang="ts">
import { Plus, Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  deleteTrainingTask,
  listTrainingTasks,
  type TrainingTask,
} from "../api/training";

const router = useRouter();
const tasks = ref<TrainingTask[]>([]);
const loading = ref(false);
const error = ref("");
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
  loading.value = true;
  error.value = "";
  try {
    tasks.value = await listTrainingTasks();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "训练任务加载失败";
  } finally {
    loading.value = false;
  }
}
async function remove(task: TrainingTask) {
  try {
    await ElMessageBox.confirm(
      `删除训练任务“${task.name}”？训练目录会移入工作区 .deleted，已发布模型保留。`,
      "删除训练任务",
      { type: "warning" },
    );
  } catch {
    return;
  }
  try {
    await deleteTrainingTask(task.id);
    ElMessage.success("训练任务已逻辑删除");
    await load();
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : "删除失败");
  }
}
onMounted(load);
</script>
<template>
  <main class="content-page training-tasks-page">
    <header class="content-toolbar">
      <div class="content-toolbar-title">
        <h1>训练任务</h1>
        <span>{{ tasks.length }} 个任务 · 最近训练优先</span>
      </div>
      <div>
        <el-button :icon="Refresh" @click="load">刷新</el-button
        ><el-button
          type="primary"
          :icon="Plus"
          @click="router.push('/training-tasks/new')"
          >新建训练任务</el-button
        >
      </div>
    </header>
    <div class="content-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <section v-loading="loading" class="task-index">
        <header v-if="tasks.length" class="task-row task-head">
          <span>训练任务</span><span>模式</span><span>状态 / 进度</span
          ><span>最近训练</span><span />
        </header>
        <article v-for="task in tasks" :key="task.id" class="task-row">
          <div class="task-name">
            <code>{{ task.code }}</code
            ><strong>{{ task.name }}</strong>
            <p>{{ task.description || `${task.model_count} 个模型` }}</p>
          </div>
          <el-tag effect="plain">{{
            task.mode === "single_model"
              ? "单模型"
              : task.mode === "single_device_serial"
                ? "单算力串行"
                : "自定义序列"
          }}</el-tag>
          <div class="task-progress">
            <span
              ><el-tag
                :type="
                  task.status === 'succeeded'
                    ? 'success'
                    : task.status === 'failed' || task.status === 'start_failed'
                      ? 'danger'
                      : task.status === 'running'
                        ? 'warning'
                        : 'info'
                "
                >{{ labels[task.status] }}</el-tag
              ><b>{{ task.progress.toFixed(1) }}%</b></span
            ><el-progress
              :percentage="task.progress"
              :show-text="false"
              :stroke-width="5"
            />
          </div>
          <time>{{
            (task.last_run_at || task.created_at).slice(0, 16).replace("T", " ")
          }}</time>
          <div class="actions">
            <router-link :to="`/training-tasks/${task.id}`">详情</router-link
            ><router-link
              v-if="task.status === 'draft' && task.can_manage"
              :to="`/training-tasks/${task.id}/edit`"
              >编辑</router-link
            ><el-button
              v-if="
                task.can_manage &&
                !['queued', 'running', 'canceling'].includes(task.status)
              "
              type="danger"
              link
              @click="remove(task)"
              >删除</el-button
            >
          </div>
        </article>
        <el-empty v-if="!loading && !tasks.length" description="还没有训练任务"
          ><el-button type="primary" @click="router.push('/training-tasks/new')"
            >新建训练任务</el-button
          ></el-empty
        >
      </section>
    </div>
  </main>
</template>
<style scoped>
.training-tasks-page {
  background: #f4f7fa;
}
.task-index {
  margin-top: 20px;
  background: white;
  border: 1px solid #d8dee6;
}
.task-row {
  display: grid;
  grid-template-columns: minmax(270px, 1.4fr) 120px minmax(
      180px,
      0.8fr
    ) 145px 150px;
  gap: 18px;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e9ef;
}
.task-head {
  color: #687482;
  font-size: 12px;
  background: #f8fafc;
}
.task-name {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 3px 12px;
}
.task-name code {
  grid-row: 1/3;
  color: #16866f;
  font-size: 12px;
}
.task-name p {
  grid-column: 2;
  margin: 0;
  color: #687482;
  font-size: 12px;
}
.task-progress span,
.actions {
  display: flex;
  align-items: center;
  gap: 9px;
}
.task-progress b {
  font-size: 12px;
}
.actions a {
  color: #2563eb;
  text-decoration: none;
}
time {
  color: #687482;
  font-size: 12px;
}
@media (max-width: 1000px) {
  .task-row {
    grid-template-columns: 1fr auto;
  }
  .task-row > :nth-child(2),
  .task-row > :nth-child(4),
  .task-head {
    display: none;
  }
}
</style>
