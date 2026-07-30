<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import {
  datasetExportDownloadUrl,
  deleteDatasetExport,
  getDatasetExport,
  listDatasetExports,
  type DatasetExport,
  type DatasetExportDetail,
  type DatasetExportStatus,
} from '../api/datasetExports'
import type { Project } from '../api/projects'

const props = defineProps<{ project: Project }>()
const items = ref<DatasetExport[]>([])
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const loading = ref(false)
const error = ref('')
const detail = ref<DatasetExportDetail | null>(null)
const detailLoading = ref(false)
const deleting = ref('')
const canEdit = computed(() => props.project.role !== 'viewer')
const manifestText = computed(() => (
  detail.value?.manifest ? JSON.stringify(detail.value.manifest, null, 2) : ''
))
const statusLabels: Record<DatasetExportStatus, string> = {
  queued: '排队中',
  running: '导出中',
  ready: '可用',
  failed: '失败',
  canceled: '已取消',
}
const exclusionLabels: Record<string, string> = {
  video_disabled: '视频停用',
  video_not_ready: '视频不可用',
  no_sampled_frames: '未抽帧',
  no_enabled_frames: '无启用帧',
  created_after_export: '快照后新增',
}

function statusType(status: DatasetExportStatus) {
  if (status === 'ready') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'primary'
  if (status === 'canceled') return 'warning'
  return 'info'
}

function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : '—'
}

function ratio(value: number | null) {
  return value === null ? '—' : `${value.toFixed(2)} : ${(1 - value).toFixed(2)}`
}

async function load(nextPage = page.value) {
  loading.value = true
  error.value = ''
  try {
    const result = await listDatasetExports(props.project.id, nextPage, pageSize.value)
    items.value = result.items
    page.value = result.page
    total.value = result.total
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '数据集列表加载失败'
  } finally {
    loading.value = false
  }
}

async function showDetail(item: DatasetExport) {
  detailLoading.value = true
  error.value = ''
  try {
    detail.value = await getDatasetExport(props.project.id, item.id)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '数据集详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

async function remove(item: DatasetExport) {
  try {
    await ElMessageBox.confirm(
      `逻辑删除数据集“${item.name}”？产物会移动到工作区 .deleted 目录。`,
      '删除数据集',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  deleting.value = item.id
  try {
    await deleteDatasetExport(props.project.id, item.id)
    ElMessage.success('数据集已移至逻辑删除目录。')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '数据集删除失败')
  } finally {
    deleting.value = ''
  }
}

function refreshAfterTask() {
  void load()
}

onMounted(() => {
  void load()
  window.addEventListener('vdm:tasks-settled', refreshAfterTask)
})
onUnmounted(() => window.removeEventListener('vdm:tasks-settled', refreshAfterTask))
</script>

<template>
  <main class="datasets-view">
    <header class="workspace-toolbar">
      <div><h1>数据集管理</h1><span>{{ total }} 个导出产物</span></div>
    </header>

    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <section v-loading="loading" class="datasets-table">
      <el-table v-if="items.length" :data="items" row-key="id">
        <el-table-column prop="name" label="数据集名称" min-width="180" />
        <el-table-column label="状态" width="94">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" effect="light">
              {{ statusLabels[row.status as DatasetExportStatus] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="导出时间" width="180">
          <template #default="{ row }">{{ dateTime(row.completed_at || row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="类别" min-width="180">
          <template #default="{ row }">
            <el-popover trigger="click" width="280">
              <template #reference>
                <el-button text>{{ row.labels.filter((label: { enabled: boolean }) => label.enabled).slice(0, 3).map((label: { name: string }) => label.name).join(', ') || '无' }}</el-button>
              </template>
              <div class="category-popover">
                <span v-for="label in row.labels" :key="label.source_label_id" :data-enabled="label.enabled">
                  {{ label.mapping }} · {{ label.name }}{{ label.enabled ? '' : '（停用）' }}
                </span>
              </div>
            </el-popover>
          </template>
        </el-table-column>
        <el-table-column label="样本帧" width="180">
          <template #default="{ row }">{{ row.total_frames }} / {{ row.train_frames }} / {{ row.val_frames }}</template>
        </el-table-column>
        <el-table-column label="期望 / 实际比例" width="210">
          <template #default="{ row }">{{ ratio(row.train_ratio) }} / {{ ratio(row.actual_train_ratio) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button :data-test="`detail-${row.id}`" text @click="showDetail(row)">详情</el-button>
              <a
                v-if="row.status === 'ready'"
                :data-test="`download-${row.id}`"
                :href="datasetExportDownloadUrl(project.id, row.id)"
              >下载</a>
              <el-button
                v-if="canEdit"
                :data-test="`delete-${row.id}`"
                text
                type="danger"
                :loading="deleting === row.id"
                :disabled="row.status === 'queued' || row.status === 'running'"
                @click="remove(row)"
              >删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div v-else-if="!loading" class="empty-state">
        <h2>还没有导出的数据集</h2>
        <p>{{ canEdit ? '从原始数据页创建第一个数据集导出任务。' : '项目编辑者完成导出后会显示在这里。' }}</p>
      </div>
    </section>

    <el-pagination
      v-if="total > pageSize"
      layout="prev, pager, next"
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      @current-change="load"
    />

    <el-dialog
      append-to-body
      fullscreen
      :model-value="detail !== null || detailLoading"
      title="数据集详细信息"
      @update:model-value="!$event && (detail = null)"
    >
      <div v-loading="detailLoading" class="dataset-detail">
        <template v-if="detail">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="数据集名称">{{ detail.name }}</el-descriptions-item>
            <el-descriptions-item label="状态">{{ statusLabels[detail.status] }}</el-descriptions-item>
            <el-descriptions-item label="绝对路径" :span="2">{{ detail.absolute_path || '—' }}</el-descriptions-item>
            <el-descriptions-item label="期望比例">{{ ratio(detail.train_ratio) }}</el-descriptions-item>
            <el-descriptions-item label="实际比例">{{ ratio(detail.actual_train_ratio) }}</el-descriptions-item>
            <el-descriptions-item label="总帧 / 训练 / 验证">{{ detail.total_frames }} / {{ detail.train_frames }} / {{ detail.val_frames }}</el-descriptions-item>
            <el-descriptions-item label="导出时间">{{ dateTime(detail.completed_at) }}</el-descriptions-item>
          </el-descriptions>

          <section>
            <h2>类别映射快照</h2>
            <el-table :data="detail.labels" size="small">
              <el-table-column prop="mapping" label="映射" width="80" />
              <el-table-column prop="name" label="英文类别" />
              <el-table-column label="状态" width="100">
                <template #default="{ row }">{{ row.enabled ? '启用' : '停用' }}</template>
              </el-table-column>
            </el-table>
          </section>

          <section v-if="detail.manifest">
            <h2>视频统计</h2>
            <el-table :data="detail.manifest.video_stats" size="small" max-height="420">
              <el-table-column prop="video_short_code" label="视频 ID" width="120" />
              <el-table-column prop="title" label="视频" min-width="180" />
              <el-table-column label="集合" width="110">
                <template #default="{ row }">{{ row.split === 'excluded' ? (exclusionLabels[row.exclusion_reason] || '排除') : row.split }}</template>
              </el-table-column>
              <el-table-column prop="total_frames" label="总帧" width="80" />
              <el-table-column prop="enabled_frames" label="启用帧" width="86" />
              <el-table-column prop="disabled_frames" label="停用帧" width="86" />
              <el-table-column prop="positive_frames" label="正样本" width="86" />
              <el-table-column prop="negative_frames" label="负样本" width="86" />
            </el-table>
          </section>

          <el-collapse v-if="manifestText">
            <el-collapse-item title="查看 manifest.json" name="manifest">
              <pre>{{ manifestText }}</pre>
            </el-collapse-item>
          </el-collapse>
        </template>
      </div>
    </el-dialog>
  </main>
</template>

<style scoped>
.datasets-view { min-height: 100%; padding: 18px; background: var(--vdw-canvas); }
.workspace-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.workspace-toolbar h1 { margin: 0; font-size: 20px; }
.workspace-toolbar span { color: var(--vdw-muted); font-size: 13px; }
.datasets-table { min-height: 260px; background: white; border: 1px solid var(--vdw-rule); }
.row-actions { display: flex; align-items: center; gap: 4px; }
.row-actions a { padding: 6px 8px; color: var(--vdw-teal); text-decoration: none; }
.category-popover { display: grid; gap: 7px; }
.category-popover span[data-enabled='false'] { color: var(--vdw-muted); }
.dataset-detail { display: grid; gap: 22px; padding: 0 4px 24px; }
.dataset-detail section h2 { margin: 0 0 10px; font-size: 17px; }
.dataset-detail pre { max-height: 420px; margin: 0; padding: 14px; overflow: auto; color: #d7e3ec; background: #111820; font: 12px/1.6 var(--vdw-mono); }
.empty-state { padding: 72px 20px; text-align: center; }
.empty-state h2 { margin: 0 0 8px; font-size: 18px; }
.empty-state p { color: var(--vdw-muted); }
</style>
