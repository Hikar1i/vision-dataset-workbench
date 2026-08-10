<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'

import { getOverview, type Overview } from '../api/overview'
import PageHeader from '../components/PageHeader.vue'
import VBar from '../ui/VBar.vue'
import VButton from '../ui/VButton.vue'
import VMetric from '../ui/VMetric.vue'
import VPanel from '../ui/VPanel.vue'
import VTag from '../ui/VTag.vue'
import { trainingStatus } from '../ui/status'

const data = ref<Overview | null>(null)
const error = ref('')
const loading = ref(false)

/** 任务状态分布。原实现用 echarts 画 5 个柱，首屏为此加载 564 kB；
 *  这里改为原生条形，同时补上 echarts 缺失的状态名中文与占比。 */
const statusRows = computed(() => {
  const rows = data.value?.task_status ?? []
  const total = rows.reduce((sum, row) => sum + row.count, 0)
  return {
    total,
    items: rows
      // 计数为 0 的状态不占一行：空行只会稀释真正有任务的状态
      .filter((row) => row.count > 0)
      .map((row) => ({
        ...row,
        ...trainingStatus(row.status),
        share: total ? (row.count / total) * 100 : 0,
      }))
      .sort((left, right) => right.count - left.count),
  }
})

const runningNote = computed(() => {
  const running = data.value?.running_tasks
  if (!running) return ''
  if (!running.global) return '当前没有进行中的训练'
  return running.own
    ? `你有 ${running.own} 个训练进行中，全局 ${running.global} 个`
    : `全局 ${running.global} 个训练进行中，其中没有你的任务`
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await getOverview()
  } catch (reason) {
    data.value = null
    error.value = reason instanceof Error ? reason.message : '看板加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="content-page">
    <PageHeader title="系统总览" kind="overview">
      <template #meta>
        <span data-test="page-stat">{{ runningNote || '系统运行总览' }}</span>
      </template>
      <template #actions>
        <VButton data-test="overview-refresh" :loading="loading" @click="load">
          <template #icon><el-icon><Refresh /></el-icon></template>
          刷新
        </VButton>
      </template>
    </PageHeader>

    <div v-loading="loading" class="content-body overview-body">
      <el-alert
        v-if="error"
        data-test="overview-error"
        :title="error"
        type="error"
        show-icon
        :closable="false"
      />
      <template v-else-if="data">
        <div data-test="overview-stats" class="overview-metrics">
          <VMetric label="数据集项目" :value="data.projects" to="/projects" reticle />
          <VMetric label="视频资源" :value="data.videos" to="/projects" />
          <VMetric label="模型项目" :value="data.model_projects" to="/model-projects" />
          <VMetric label="训练任务" :value="data.training_tasks" to="/training-tasks">
            <VTag v-if="data.running_tasks.global" tone="run">
              {{ data.running_tasks.global }} 个进行中
            </VTag>
            <span v-else>全部空闲</span>
          </VMetric>
        </div>

        <div class="overview-grid">
          <VPanel title="训练任务状态">
            <template #actions>
              <VButton variant="quiet" size="sm" @click="$router.push('/training-tasks')">
                查看全部
              </VButton>
            </template>
            <div v-if="statusRows.items.length" class="status-list">
              <div v-for="row in statusRows.items" :key="row.status" class="status-row">
                <div class="status-row__line">
                  <VTag :tone="row.tone">{{ row.label }}</VTag>
                  <b class="vdw-num">{{ row.count }}</b>
                </div>
                <VBar :value="row.share" :tone="row.tone" :label="`${row.label} ${row.count} 个`" />
              </div>
            </div>
            <p v-else class="overview-note">还没有训练任务。</p>
            <template v-if="statusRows.total" #footer>
              <span>合计 <b class="vdw-num">{{ statusRows.total }}</b> 个训练任务</span>
            </template>
          </VPanel>

          <VPanel title="当前负载">
            <dl class="load-list">
              <div>
                <dt>我的进行中任务</dt>
                <dd class="vdw-num">{{ data.running_tasks.own }}</dd>
              </div>
              <div>
                <dt>全局进行中任务</dt>
                <dd class="vdw-num">{{ data.running_tasks.global }}</dd>
              </div>
            </dl>
            <template #footer>
              <span>{{ data.host.note }} <code>{{ data.host.hostname }}</code></span>
            </template>
          </VPanel>
        </div>
      </template>
    </div>
  </main>
</template>

<style scoped>
.overview-body {
  display: grid;
  gap: 14px;
  align-content: start;
}

.overview-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.status-list {
  display: grid;
  gap: 13px;
}

.status-row__line {
  display: flex;
  align-items: center;
  margin-bottom: 7px;
  font-size: 14px;
}

.status-row__line b {
  margin-left: auto;
  font-weight: 500;
}

.overview-note {
  margin: 0;
  color: var(--vdw-ink-2);
  font-size: 14px;
}

.load-list {
  display: grid;
  gap: 14px;
  margin: 0;
}

.load-list div + div {
  padding-top: 14px;
  border-top: 1px solid var(--vdw-line);
}

.load-list dt {
  color: var(--vdw-ink-3);
  font: 500 13px/1 var(--vdw-mono);
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.load-list dd {
  margin: 10px 0 0;
  font-size: 26px;
  font-weight: 500;
}

/* 2560px 下让指标与面板吸收宽度，不放大控件与文字 */
@media (min-width: 2200px) {
  .overview-metrics {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
