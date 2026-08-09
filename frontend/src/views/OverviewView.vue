<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { getOverview, type Overview } from '../api/overview'
import PageHeader from '../components/PageHeader.vue'

const data = ref<Overview | null>(null)
const error = ref('')
const loading = ref(false)
const chart = ref<HTMLElement | null>(null)
let chartInstance: echarts.ECharts | null = null
function renderChart() {
  if (!chart.value || !data.value) return
  chartInstance?.dispose(); chartInstance = echarts.init(chart.value)
  chartInstance.setOption({ tooltip: { trigger: 'axis' }, grid: { left: 40, right: 20, top: 20, bottom: 30 }, xAxis: { type: 'category', data: data.value.task_status.map((item) => item.status) }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: data.value.task_status.map((item) => item.count), itemStyle: { color: '#4f7cff' } }] })
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await getOverview()
    await nextTick()
    renderChart()
  } catch (reason) {
    data.value = null
    error.value = reason instanceof Error ? reason.message : '看板加载失败'
  } finally {
    loading.value = false
  }
}
onMounted(load)
onBeforeUnmount(() => chartInstance?.dispose())
</script>

<template>
  <main class="content-page overview-page">
    <PageHeader title="Overview"><template #meta><span data-test="page-stat">系统运行总览</span></template><template #actions><el-button data-test="overview-refresh" :loading="loading" @click="load">刷新</el-button></template></PageHeader>
    <div v-loading="loading" class="content-body overview-body">
      <el-alert v-if="error" data-test="overview-error" :title="error" type="error" :closable="false" />
      <template v-else-if="data">
        <div data-test="overview-stats" class="stat-grid">
          <el-card><strong>{{ data.projects }}</strong><span>我的数据集项目</span></el-card><el-card><strong>{{ data.videos }}</strong><span>视频资源</span></el-card><el-card><strong>{{ data.model_projects }}</strong><span>模型项目</span></el-card><el-card><strong>{{ data.training_tasks }}</strong><span>我的训练任务</span></el-card>
        </div>
        <div class="dashboard-grid">
          <el-card><template #header>训练任务状态</template><div ref="chart" class="chart" /></el-card>
          <el-card><template #header>当前负载</template><div class="load-item"><span>我的进行中任务</span><strong>{{ data.running_tasks.own }}</strong></div><div class="load-item"><span>全局进行中任务</span><strong>{{ data.running_tasks.global }}</strong></div><p class="muted">{{ data.host.note }}：{{ data.host.hostname }}</p></el-card>
        </div>
      </template>
    </div>
  </main>
</template>

<style scoped>
.overview-body { padding: 20px; overflow: auto; }.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }.stat-grid strong { display: block; font-size: 32px; color: var(--vdw-accent); }.stat-grid span { color: var(--vdw-muted); }.dashboard-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; }.chart { height: 300px; }.load-item { display:flex; justify-content:space-between; padding: 14px 0; border-bottom: 1px solid var(--el-border-color-lighter); }.muted { color: var(--vdw-muted); font-size: 12px; }
@media (max-width: 960px) { .stat-grid { grid-template-columns: repeat(2, 1fr); }.dashboard-grid { grid-template-columns: 1fr; } }
</style>
