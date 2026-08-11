<script setup lang="ts">
import {
  Delete, EditPen, Plus, Refresh, RefreshLeft, RefreshRight, VideoPlay, View,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  deleteTrainingTask,
  listTrainingTasks,
  retryFailedTrainingModels,
  resumeInterruptedTrainingModels,
  startTrainingTask,
  type TrainingTask,
} from '../api/training'
import PageHeader from '../components/PageHeader.vue'
import VBar from '../ui/VBar.vue'
import VButton from '../ui/VButton.vue'
import VCellName from '../ui/VCellName.vue'
import VChip from '../ui/VChip.vue'
import VEmpty from '../ui/VEmpty.vue'
import VPanel from '../ui/VPanel.vue'
import VRow from '../ui/VRow.vue'
import VTable from '../ui/VTable.vue'
import VTag from '../ui/VTag.vue'
import { trainingStatus } from '../ui/status'

type Filter = 'all' | 'running' | 'failed' | 'draft'

const router = useRouter()
const tasks = ref<TrainingTask[]>([])
const loading = ref(false)
const busy = ref<Record<string, boolean>>({})
const error = ref('')
const filter = ref<Filter>('all')

const COLUMNS =
  'minmax(240px, auto) 80px minmax(180px, auto) 128px 128px minmax(232px, auto)'

const MODE_LABEL: Record<string, string> = {
  single_model: '单模型',
  single_device_serial: '单算力串行',
  custom_sequence: '自定义序列',
}

const RUNNING = new Set(['queued', 'running', 'canceling'])
const FAILED = new Set(['failed', 'start_failed', 'partial'])

const counts = computed(() => ({
  all: tasks.value.length,
  running: tasks.value.filter((task) => RUNNING.has(task.status)).length,
  failed: tasks.value.filter((task) => FAILED.has(task.status)).length,
  draft: tasks.value.filter((task) => task.status === 'draft').length,
}))

const visible = computed(() => {
  if (filter.value === 'all') return tasks.value
  if (filter.value === 'running') return tasks.value.filter((t) => RUNNING.has(t.status))
  if (filter.value === 'failed') return tasks.value.filter((t) => FAILED.has(t.status))
  return tasks.value.filter((task) => task.status === 'draft')
})

/**
 * 每行只提升一个操作为 default——该行当前最合理的下一步。
 * 其余保持 quiet，禁用项不画底色。重构前 6 个操作等重并列，
 * 且禁用项比可用项更显眼。
 */
function primaryAction(task: TrainingTask): 'start' | 'retry' | 'resume' | null {
  if (!task.can_manage) return null
  if (task.actions.resume?.allowed) return 'resume'
  if (task.actions.retry?.allowed) return 'retry'
  if (task.actions.start?.allowed) return 'start'
  return null
}

const stamp = (value: string | null | undefined) =>
  (value ? value.slice(0, 16).replace('T', ' ') : '')

async function load() {
  loading.value = true
  error.value = ''
  try {
    tasks.value = await listTrainingTasks()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '训练任务加载失败'
  } finally {
    loading.value = false
  }
}

async function remove(task: TrainingTask) {
  try {
    await ElMessageBox.confirm(
      `删除训练任务“${task.name}”？训练目录会移入工作区 .deleted，已发布模型保留。`,
      '删除训练任务',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await deleteTrainingTask(task.id)
    ElMessage.success('训练任务已逻辑删除')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '删除失败')
  }
}

async function runAction(task: TrainingTask, action: 'start' | 'retry' | 'resume') {
  busy.value = { ...busy.value, [task.id]: true }
  try {
    if (action === 'start') await startTrainingTask(task.id)
    else if (action === 'retry') await retryFailedTrainingModels(task.id)
    else await resumeInterruptedTrainingModels(task.id)
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '操作失败')
  } finally {
    busy.value = { ...busy.value, [task.id]: false }
  }
}

onMounted(load)
</script>

<template>
  <main class="content-page">
    <PageHeader title="训练任务" kind="training tasks">
      <template #meta>
        <span data-test="page-stat">{{ tasks.length }} 个任务 · 最近训练优先</span>
      </template>
      <template #actions>
        <VButton :loading="loading" @click="load">
          <template #icon><el-icon><Refresh /></el-icon></template>
          刷新
        </VButton>
        <VButton variant="primary" @click="router.push('/training-tasks/new')">
          <template #icon><el-icon><Plus /></el-icon></template>
          新建训练任务
        </VButton>
      </template>
      <template #tabs>
        <button
          v-for="option in ([
            { key: 'all', label: '全部' },
            { key: 'running', label: '进行中' },
            { key: 'failed', label: '异常' },
            { key: 'draft', label: '草稿' },
          ] as Array<{ key: Filter; label: string }>)"
          :key="option.key"
          :data-test="`task-filter-${option.key}`"
          type="button"
          :class="{ 'is-active': filter === option.key }"
          :aria-selected="filter === option.key"
          @click="filter = option.key"
        >
          {{ option.label }} <span class="tab-count">{{ counts[option.key] }}</span>
        </button>
      </template>
    </PageHeader>

    <div class="content-body">
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
      <VPanel v-loading="loading" flush>
        <VTable
          :columns="COLUMNS"
          :headers="['训练任务', '模式', '状态 / 进度', '创建时间', '最近训练', '操作']"
        >
          <VRow v-for="task in visible" :key="task.id" :columns="COLUMNS">
            <VCellName
              :name="task.name"
              :sub="task.description || `${task.model_count} 个模型`"
            >
              <template #badge><VChip variant="id">{{ task.code }}</VChip></template>
            </VCellName>

            <VChip>{{ MODE_LABEL[task.mode] ?? task.mode }}</VChip>

            <div>
              <div class="task-progress">
                <VTag :tone="trainingStatus(task.status).tone">
                  {{ trainingStatus(task.status).label }}
                </VTag>
                <span class="vdw-num task-progress__value">
                  {{ task.status === 'draft' ? '—' : `${task.progress.toFixed(1)}%` }}
                </span>
              </div>
              <VBar
                v-if="task.status !== 'draft'"
                :value="task.progress"
                :tone="trainingStatus(task.status).tone"
                :label="`${task.name} 进度`"
              />
            </div>

            <time>{{ stamp(task.created_at) }}</time>
            <time :class="{ 'is-empty': !task.last_run_at }">
              {{ task.last_run_at ? stamp(task.last_run_at) : '尚未开始' }}
            </time>

            <div class="row-actions">
              <VButton
                variant="quiet"
                size="sm"
                @click="router.push(`/training-tasks/${task.id}`)"
              ><template #icon><el-icon><View /></el-icon></template>详情</VButton>
              <VButton
                variant="quiet"
                size="sm"
                :disabled="!task.actions.edit?.allowed || !task.can_manage"
                :title="task.actions.edit?.message || '编辑训练草稿'"
                @click="router.push(`/training-tasks/${task.id}/edit`)"
              ><template #icon><el-icon><EditPen /></el-icon></template>编辑</VButton>
              <VButton
                v-for="action in ([
                  { key: 'start', label: '开始', fallback: '开始训练', icon: VideoPlay },
                  { key: 'retry', label: '重试', fallback: '重试失败', icon: RefreshRight },
                  { key: 'resume', label: '恢复', fallback: '恢复中断', icon: RefreshLeft },
                ] as const)"
                :key="action.key"
                :variant="primaryAction(task) === action.key ? 'default' : 'quiet'"
                size="sm"
                :loading="busy[task.id] && primaryAction(task) === action.key"
                :disabled="!task.can_manage || !task.actions[action.key]?.allowed"
                :title="task.actions[action.key]?.message || action.fallback"
                @click="runAction(task, action.key)"
              ><template #icon><el-icon><component :is="action.icon" /></el-icon></template>{{ action.label }}</VButton>
              <VButton
                variant="danger"
                size="sm"
                :disabled="!task.can_manage || !task.actions.delete?.allowed"
                :title="task.actions.delete?.message || '删除任务'"
                @click="remove(task)"
              ><template #icon><el-icon><Delete /></el-icon></template>删除</VButton>
            </div>
          </VRow>

          <template #empty>
            <VEmpty
              v-if="!loading && !visible.length"
              :title="filter === 'all' ? '还没有训练任务' : '这个筛选下没有任务'"
              :note="filter === 'all'
                ? '新建训练任务后，可以为同一数据集编排多个模型依次训练。'
                : undefined"
            >
              <VButton
                v-if="filter === 'all'"
                variant="primary"
                @click="router.push('/training-tasks/new')"
              >新建训练任务</VButton>
              <VButton v-else variant="default" @click="filter = 'all'">查看全部任务</VButton>
            </VEmpty>
          </template>
        </VTable>
      </VPanel>
    </div>
  </main>
</template>

<style scoped>
.task-progress {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 7px;
}

.task-progress__value {
  font-size: 14px;
  color: var(--vdw-ink-2);
}

/* 行操作左对齐，与其它列同一起点（4.1）。原为 flex-end，操作列孤零零贴右边，
   与左对齐的表头对不上。 */
.row-actions {
  display: flex;
  gap: 2px;
}

time {
  font-size: 14px;
  color: var(--vdw-ink-2);
}

time.is-empty {
  color: var(--vdw-ink-3);
}
</style>
