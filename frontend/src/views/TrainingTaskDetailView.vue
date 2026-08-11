<script setup lang="ts">
import { ArrowDown, Close, Delete, Plus, RefreshLeft, RefreshRight, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  cancelTrainingModel,
  cancelTrainingTask,
  deleteTrainingModel,
  deleteTrainingTask,
  deriveTrainingTask,
  getTrainingTask,
  retryFailedTrainingModels,
  retryTrainingModel,
  resumeInterruptedTrainingModels,
  resumeTrainingModel,
  startTrainingTask,
  type TrainingModel,
  type TrainingTask,
} from '../api/training'
import PageHeader from '../components/PageHeader.vue'
import {
  forgetResource,
  rememberResource,
} from '../navigation/recentResources'
import VBar from '../ui/VBar.vue'
import VButton from '../ui/VButton.vue'
import VChip from '../ui/VChip.vue'
import VPanel from '../ui/VPanel.vue'
import VRow from '../ui/VRow.vue'
import VTable from '../ui/VTable.vue'
import VTag from '../ui/VTag.vue'
import { trainingStatus } from '../ui/status'

const route = useRoute()
const router = useRouter()
const task = ref<TrainingTask>()
const error = ref('')
let timer: number | undefined
let loadVersion = 0

const COLUMNS =
  '52px minmax(240px, 1.2fr) 104px minmax(180px, 0.9fr) minmax(200px, 0.9fr) minmax(390px, 1.8fr)'

const MODE_LABEL: Record<string, string> = {
  single_model: '单模型',
  single_device_serial: '单算力串行',
  custom_sequence: '自定义序列',
}

const active = computed(
  () => task.value && ['queued', 'running', 'canceling'].includes(task.value.status),
)

const groups = computed(() => {
  const map = new Map<number, NonNullable<TrainingTask['models']>>()
  for (const model of task.value?.models || []) {
    const lane = map.get(model.gpu_index) || []
    lane.push(model)
    map.set(model.gpu_index, lane)
  }
  return [...map.entries()]
})

/** 摘要项。原实现是 8 个等重的英文标签块，这里保留信息但压成两行读得完的摘要。 */
const summary = computed(() => {
  if (!task.value) return []
  const value = task.value
  return [
    { key: '模式', text: MODE_LABEL[value.mode] ?? value.mode },
    { key: '创建', text: formatTime(value.created_at) },
    { key: '开始', text: formatTime(value.started_at) },
    { key: '持续', text: duration(value.started_at, value.finished_at) },
    { key: '结束', text: formatTime(value.finished_at) },
  ]
})

async function load() {
  const version = ++loadVersion
  const id = String(route.params.id)
  try {
    const nextTask = await getTrainingTask(id)
    if (version !== loadVersion) return
    task.value = nextTask
    error.value = ''
    rememberResource('vdm.recent-training-tasks', nextTask)
  } catch (e) {
    if (version !== loadVersion) return
    error.value = e instanceof Error ? e.message : '训练任务加载失败'
  }
}

function loadRouteTask() {
  task.value = undefined
  error.value = ''
  void load()
}

async function cancel() {
  try {
    await ElMessageBox.confirm(
      '取消后，排队模型立即取消，运行模型会先终止进程。已生成的 last.pt 将按规则保留。',
      '取消训练任务',
      { type: 'warning' },
    )
    task.value = await cancelTrainingTask(String(route.params.id))
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message)
  }
}

async function start() {
  if (!task.value) return
  try {
    task.value = await startTrainingTask(task.value.id)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '启动失败')
  }
}

async function resumeInterrupted() {
  if (!task.value) return
  try {
    await ElMessageBox.confirm('仅恢复具有有效 last.pt 的中断模型。', '恢复中断模型')
    task.value = await resumeInterruptedTrainingModels(task.value.id)
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message)
  }
}

async function modelAction(
  model: TrainingModel,
  action: 'cancel' | 'retry' | 'resume' | 'delete',
) {
  try {
    if (action === 'cancel') await cancelTrainingModel(model.id)
    else if (action === 'resume') await resumeTrainingModel(model.id)
    else if (action === 'retry') {
      let confirm = false
      if (model.status === 'succeeded') {
        await ElMessageBox.confirm(
          '该模型已成功发布，重试成功后将覆盖当前发布模型。',
          '确认重试成功模型',
          { type: 'warning' },
        )
        confirm = true
      }
      await retryTrainingModel(model.id, confirm)
    } else {
      await ElMessageBox.confirm(
        '删除会归档该模型运行目录；已发布模型也会逻辑删除。',
        '删除训练模型',
        { type: 'warning' },
      )
      await deleteTrainingModel(model.id, model.status === 'succeeded')
    }
    await load()
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message)
  }
}

function formatTime(value: string | null | undefined) {
  return value ? value.slice(0, 19).replace('T', ' ') : '—'
}

function duration(started: string | null | undefined, finished: string | null | undefined) {
  if (!started) return '—'
  const seconds = Math.max(
    0,
    Math.floor(((finished ? Date.parse(finished) : Date.now()) - Date.parse(started)) / 1000),
  )
  return `${Math.floor(seconds / 3600)}h ${String(Math.floor((seconds % 3600) / 60)).padStart(2, '0')}m ${String(seconds % 60).padStart(2, '0')}s`
}

async function remove() {
  try {
    await ElMessageBox.confirm(
      '训练任务配置、运行日志和未发布 checkpoint 将移入 .deleted；已发布模型不会删除。',
      '删除训练任务',
      { type: 'warning' },
    )
    await deleteTrainingTask(String(route.params.id))
    forgetResource('vdm.recent-training-tasks', String(route.params.id))
    await router.push('/training-tasks')
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message)
  }
}

async function retryFailed() {
  try {
    await ElMessageBox.confirm(
      '只为失败、启动异常或已取消的模型创建新运行；成功模型保持不变。',
      '重试未成功模型',
    )
    task.value = await retryFailedTrainingModels(String(route.params.id))
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message)
  }
}

async function derive() {
  if (!task.value) return
  try {
    const result = await ElMessageBox.prompt(
      '填写新任务 code。派生任务固定使用每个模型原来的数据集与 basemodel，仅允许后续修改超参数。',
      '派生训练任务',
      {
        inputPattern: /^[a-z][a-z0-9-]{2,31}$/,
        inputErrorMessage: '请输入 3–32 位小写字母、数字或连字符',
      },
    )
    const created = await deriveTrainingTask(task.value.id, {
      task_code: result.value,
      task_name: `${task.value.name} 派生`,
      description: task.value.description,
    })
    await router.push(`/training-tasks/${created.id}/edit`)
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message)
  }
}

function handleMore(command: 'derive' | 'retry' | 'resume' | 'cancel' | 'delete') {
  if (command === 'derive') return void derive()
  if (command === 'retry') return void retryFailed()
  if (command === 'resume') return void resumeInterrupted()
  if (command === 'cancel') return void cancel()
  return void remove()
}

watch(() => route.params.id, loadRouteTask, { immediate: true })
onMounted(() => {
  timer = window.setInterval(() => {
    if (active.value) void load()
  }, 1500)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <main class="content-page">
    <PageHeader
      :title="task?.name || '训练任务'"
      kind="training task"
      :code="task?.code"
      back-to="/training-tasks"
      back-label="返回训练任务"
    >
      <template v-if="task" #meta>
        <span>{{ task.model_count }} 个模型 · {{ MODE_LABEL[task.mode] ?? task.mode }}</span>
      </template>
      <template v-if="task" #actions>
        <VButton
          :disabled="!task.can_manage || !task.actions.edit?.allowed"
          :title="task.actions.edit?.message || '编辑训练草稿'"
          @click="router.push(`/training-tasks/${task.id}/edit`)"
        >编辑草稿</VButton>
        <VButton
          variant="primary"
          :disabled="!task.can_manage || !task.actions.start?.allowed"
          :title="task.actions.start?.message || '开始训练'"
          @click="start"
        >开始训练</VButton>
        <!-- 其余 5 个操作收进"更多"，头部不再并排 7 个等重按钮 -->
        <el-dropdown trigger="click" placement="bottom-end" @command="handleMore">
          <VButton>
            更多
            <template #icon><el-icon><ArrowDown /></el-icon></template>
          </VButton>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                command="derive"
                :disabled="!task.can_manage || !task.actions.derive?.allowed"
              >派生任务</el-dropdown-item>
              <el-dropdown-item
                command="retry"
                :disabled="!task.can_manage || !task.actions.retry?.allowed"
              >重试未成功模型</el-dropdown-item>
              <el-dropdown-item
                command="resume"
                :disabled="!task.can_manage || !task.actions.resume?.allowed"
              >恢复中断模型</el-dropdown-item>
              <el-dropdown-item
                command="cancel"
                divided
                :disabled="!task.can_manage || !task.actions.cancel?.allowed"
              >取消任务</el-dropdown-item>
              <el-dropdown-item
                command="delete"
                :disabled="!task.can_manage || !task.actions.delete?.allowed"
              >删除任务</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>
    </PageHeader>

    <div class="content-body detail-body">
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

      <template v-if="task">
        <VPanel>
          <div class="run-hero">
            <div class="run-hero__state">
              <VTag :tone="trainingStatus(task.status).tone">
                {{ trainingStatus(task.status).label }}
              </VTag>
              <b class="vdw-num">{{ task.progress.toFixed(1) }}%</b>
            </div>
            <VBar
              :value="task.progress"
              :tone="trainingStatus(task.status).tone"
              label="任务总进度"
            />
            <dl class="run-summary">
              <div v-for="item in summary" :key="item.key">
                <dt>{{ item.key }}</dt>
                <dd>{{ item.text }}</dd>
              </div>
            </dl>
          </div>
        </VPanel>

        <VPanel v-for="[gpu, models] in groups" :key="gpu" flush>
          <template #head>
            <h2>GPU {{ gpu }}</h2>
            <VChip>{{ models.length }} 个模型 · 同卡严格串行</VChip>
          </template>
          <VTable
            :columns="COLUMNS"
            :headers="['顺序', '模型', '状态', '进度', '运行信息', '操作']"
          >
            <VRow v-for="model in models" :key="model.id" :columns="COLUMNS">
              <span class="lane-order">q{{ String(model.queue_order).padStart(2, '0') }}</span>

              <div class="model-identity">
                <b>{{ model.name }}</b>
                <code>{{ model.artifact_code || '启动时冻结产物名' }}</code>
              </div>

              <VTag :tone="trainingStatus(model.status).tone">
                {{ trainingStatus(model.status).label }}
              </VTag>

              <div>
                <div class="model-epoch">
                  <span class="vdw-num">
                    {{ model.runs[0]?.current_epoch || 0 }} /
                    {{ model.runs[0]?.target_epochs || '—' }}
                  </span>
                  <span class="model-epoch__unit">epoch</span>
                </div>
                <VBar
                  :value="model.progress"
                  :tone="trainingStatus(model.status).tone"
                  :label="`${model.name} 进度`"
                />
              </div>

              <div class="run-meta">
                <span v-if="model.runs[0]?.pid">PID {{ model.runs[0].pid }}</span>
                <span>开始 {{ formatTime(model.started_at) }}</span>
                <span>持续 {{ duration(model.started_at, model.finished_at) }}</span>
              </div>

              <div class="row-actions">
                <VButton
                  variant="default"
                  size="sm"
                  @click="router.push(`/training-tasks/${task.id}/models/${model.id}`)"
                ><template #icon><el-icon><View /></el-icon></template>详情</VButton>
                <VButton
                  variant="quiet"
                  size="sm"
                  :disabled="!model.actions.cancel?.allowed"
                  :title="model.actions.cancel?.message || '取消'"
                  @click="modelAction(model, 'cancel')"
                ><template #icon><el-icon><Close /></el-icon></template>取消</VButton>
                <VButton
                  variant="quiet"
                  size="sm"
                  :disabled="!model.actions.retry?.allowed"
                  :title="model.actions.retry?.message || '重试'"
                  @click="modelAction(model, 'retry')"
                ><template #icon><el-icon><RefreshRight /></el-icon></template>重试</VButton>
                <VButton
                  variant="quiet"
                  size="sm"
                  :disabled="!model.actions.resume?.allowed"
                  :title="model.actions.resume?.message || '恢复中断'"
                  @click="modelAction(model, 'resume')"
                ><template #icon><el-icon><RefreshLeft /></el-icon></template>恢复</VButton>
                <VButton
                  variant="quiet"
                  size="sm"
                  :disabled="!model.actions.extend?.allowed"
                  :title="model.actions.extend?.message || '追加训练'"
                  @click="router.push(
                    `/training-tasks/${task.id}/models/${model.id}?action=extend`,
                  )"
                ><template #icon><el-icon><Plus /></el-icon></template>追加</VButton>
                <VButton
                  variant="danger"
                  size="sm"
                  :disabled="!model.actions.delete?.allowed"
                  :title="model.actions.delete?.message || '删除'"
                  @click="modelAction(model, 'delete')"
                ><template #icon><el-icon><Delete /></el-icon></template>删除</VButton>
              </div>
            </VRow>
          </VTable>
        </VPanel>
      </template>
    </div>
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
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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

.lane-order {
  color: var(--vdw-accent-ink);
  font: 500 13px/1 var(--vdw-mono);
}

.model-identity {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.model-identity b {
  overflow: hidden;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-identity code {
  overflow: hidden;
  color: var(--vdw-ink-3);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-epoch {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 14px;
}

.model-epoch__unit {
  color: var(--vdw-ink-3);
  font-size: 13px;
}

.run-meta {
  display: grid;
  gap: 3px;
  color: var(--vdw-ink-2);
  font-size: 13px;
}

.row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
}
</style>
