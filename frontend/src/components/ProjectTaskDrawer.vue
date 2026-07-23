<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'

import {
  cancelTask,
  listTasks,
  retryTask,
  type ProjectTask,
} from '../api/media'

const props = defineProps<{ modelValue: boolean; projectId: string; canManage: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  settled: []
}>()
const tasks = ref<ProjectTask[]>([])
const loading = ref(false)
const changing = ref('')
const error = ref('')
let timer: ReturnType<typeof setInterval> | undefined
let knownStatuses = new Map<string, ProjectTask['status']>()

const typeLabels = { copy_video: '本地复制', download_video: '远程下载' } as const
const statusLabels = {
  queued: '排队中',
  running: '执行中',
  succeeded: '已完成',
  failed: '失败',
  canceled: '已取消',
} as const

async function load() {
  if (!props.modelValue) return
  loading.value = !tasks.value.length
  error.value = ''
  try {
    const result = await listTasks(props.projectId)
    const settled = result.items.some((task) => {
      const previous = knownStatuses.get(task.id)
      return previous && previous !== task.status && ['succeeded', 'failed', 'canceled'].includes(task.status)
    })
    tasks.value = result.items
    knownStatuses = new Map(result.items.map((task) => [task.id, task.status]))
    if (settled) emit('settled')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '任务读取失败'
  } finally {
    loading.value = false
  }
}

async function cancel(task: ProjectTask) {
  changing.value = task.id
  try {
    await cancelTask(props.projectId, task.id)
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '任务取消失败'
  } finally {
    changing.value = ''
  }
}

async function retry(task: ProjectTask) {
  changing.value = task.id
  try {
    await retryTask(props.projectId, task.id)
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '任务重试失败'
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
  (open) => {
    stopPolling()
    if (open) {
      void load()
      timer = setInterval(load, 1000)
    }
  },
  { immediate: true },
)

onUnmounted(stopPolling)
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    title="项目任务"
    size="min(520px, 100vw)"
    :teleported="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div v-loading="loading" class="task-list">
      <article v-for="task in tasks" :key="task.id" class="task-row">
        <header>
          <div><code>{{ task.id.slice(0, 8) }}</code><strong>{{ typeLabels[task.type] }}</strong></div>
          <span :data-status="task.status">{{ statusLabels[task.status] }}</span>
        </header>
        <el-progress
          :percentage="task.progress"
          :status="task.status === 'failed' ? 'exception' : task.status === 'succeeded' ? 'success' : undefined"
        />
        <p v-if="task.error">{{ task.error }}</p>
        <footer v-if="canManage">
          <el-button
            v-if="task.status === 'queued' || task.status === 'running'"
            :data-test="`cancel-${task.id}`"
            text
            :loading="changing === task.id"
            @click="cancel(task)"
          >
            取消
          </el-button>
          <el-button
            v-if="task.status === 'failed' || task.status === 'canceled'"
            :data-test="`retry-${task.id}`"
            text
            type="primary"
            :loading="changing === task.id"
            @click="retry(task)"
          >
            重试
          </el-button>
        </footer>
      </article>
      <div v-if="!loading && !tasks.length" class="empty">当前项目还没有任务。</div>
    </div>
  </el-drawer>
</template>

<style scoped>
.task-list {
  display: grid;
  gap: 12px;
}

.task-row {
  padding: 15px;
  border: 1px solid #d8dee6;
}

.task-row header,
.task-row header > div,
.task-row footer {
  display: flex;
  align-items: center;
}

.task-row header {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.task-row header > div {
  gap: 10px;
}

code {
  color: #16866f;
  font-size: 10px;
}

header > span {
  color: #687482;
  font-size: 12px;
}

header > span[data-status='failed'] {
  color: #c2413b;
}

.task-row p {
  margin: 10px 0 0;
  color: #c2413b;
  font-size: 12px;
  line-height: 1.5;
}

.task-row footer {
  justify-content: flex-end;
  margin-top: 6px;
}

.empty {
  padding: 56px 20px;
  color: #687482;
  text-align: center;
  border: 1px dashed #cbd3dd;
}
</style>
