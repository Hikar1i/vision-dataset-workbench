<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onUnmounted, ref, watch } from 'vue'

import {
  cancelTask,
  listGlobalTasks,
  retryTask,
  type GlobalProjectTask,
} from '../api/media'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  unread: [value: boolean]
  settled: []
}>()
const tasks = ref<GlobalProjectTask[]>([])
const loading = ref(false)
const changing = ref('')
const loaded = ref(false)
const latestTerminalAt = ref<string | null>(null)
let timer: ReturnType<typeof setInterval> | undefined
const lastViewedKey = 'vdm.tasks-last-viewed-at'

const typeLabels = {
  copy_video: '本地复制',
  download_video: '远程下载',
  extract_frames: '采样抽帧',
  import_model: '模型入库',
  auto_annotate: '自动标注',
  export_dataset: '数据集导出',
} as const
const statusLabels = {
  queued: '排队中',
  running: '执行中',
  succeeded: '已完成',
  failed: '失败',
  canceled: '已取消',
} as const

async function load() {
  loading.value = props.modelValue && !tasks.value.length
  try {
    const page = await listGlobalTasks()
    const previousTerminalAt = latestTerminalAt.value
    tasks.value = page.items
    latestTerminalAt.value = page.latest_terminal_at
    if (loaded.value && previousTerminalAt !== page.latest_terminal_at) emit('settled')
    loaded.value = true
    if (props.modelValue) {
      localStorage.setItem(lastViewedKey, new Date().toISOString())
      emit('unread', false)
    } else {
      const viewedAt = Date.parse(localStorage.getItem(lastViewedKey) ?? '') || 0
      emit(
        'unread',
        page.latest_terminal_at !== null && Date.parse(page.latest_terminal_at) > viewedAt,
      )
    }
  } catch (reason) {
    if (props.modelValue) ElMessage.error(reason instanceof Error ? reason.message : '任务读取失败')
  } finally {
    loading.value = false
  }
}

async function cancel(task: GlobalProjectTask) {
  changing.value = task.id
  try {
    await cancelTask(task.project_id, task.id)
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '任务取消失败')
  } finally {
    changing.value = ''
  }
}

async function retry(task: GlobalProjectTask) {
  changing.value = task.id
  try {
    await retryTask(task.project_id, task.id)
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '任务重试失败')
  } finally {
    changing.value = ''
  }
}

function stopPolling() {
  if (timer) clearInterval(timer)
  timer = undefined
}

watch(
  () => props.modelValue,
  () => {
    stopPolling()
    void load()
    timer = setInterval(load, props.modelValue ? 1000 : 10_000)
  },
  { immediate: true },
)
onUnmounted(stopPolling)
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    title="任务中心"
    size="min(616px, 100vw)"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="task-center-list">
      <article v-for="task in tasks" :key="task.id" class="task-center-row">
        <header>
          <div><strong>{{ typeLabels[task.type] }}</strong><span>{{ task.project_name }}</span></div>
          <span :data-status="task.status">{{ statusLabels[task.status] }}</span>
        </header>
        <el-progress
          :percentage="task.progress"
          :status="task.status === 'failed' ? 'exception' : task.status === 'succeeded' ? 'success' : undefined"
        />
        <p v-if="task.error">{{ task.error }}</p>
        <footer v-if="task.can_manage">
          <el-button
            v-if="task.status === 'queued' || task.status === 'running'"
            :data-test="`cancel-${task.id}`"
            text
            :loading="changing === task.id"
            @click="cancel(task)"
          >取消</el-button>
          <el-button
            v-if="(task.status === 'failed' || task.status === 'canceled') && task.type !== 'import_model' && task.type !== 'auto_annotate' && task.type !== 'export_dataset'"
            :data-test="`retry-${task.id}`"
            text
            type="primary"
            :loading="changing === task.id"
            @click="retry(task)"
          >重试</el-button>
        </footer>
      </article>
      <div v-if="!loading && !tasks.length" class="state-panel">还没有后台任务。</div>
    </div>
  </el-drawer>
</template>

<style scoped>
.task-center-list { display: grid; gap: 11px; }
.task-center-row { padding: 15px; border: 1px solid var(--vdw-rule); }
.task-center-row header,
.task-center-row header > div,
.task-center-row footer { display: flex; align-items: center; }
.task-center-row header { justify-content: space-between; gap: 13px; margin-bottom: 11px; }
.task-center-row header > div { gap: 9px; }
.task-center-row header span { color: var(--vdw-muted); font-size: 13px; }
.task-center-row p { color: #a33e39; font-size: 13px; }
.task-center-row footer { justify-content: flex-end; }
</style>
