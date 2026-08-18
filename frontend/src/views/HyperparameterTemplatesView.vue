<script setup lang="ts">
import { CopyDocument, Delete, Edit, Plus, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  deleteHyperparameterTemplate,
  listHyperparameterTemplates,
  type HyperparameterTemplate,
} from '../api/hyperparameters'
import PageHeader from '../components/PageHeader.vue'
import VButton from '../ui/VButton.vue'
import VCellName from '../ui/VCellName.vue'
import VEmpty from '../ui/VEmpty.vue'
import VPanel from '../ui/VPanel.vue'
import VRow from '../ui/VRow.vue'
import VTable from '../ui/VTable.vue'
import VTag from '../ui/VTag.vue'

const router = useRouter()
const templates = ref<HyperparameterTemplate[]>([])
const loading = ref(false)
const deleting = ref('')
const error = ref('')

const COLUMNS = 'minmax(250px, 1fr) 80px 80px 90px 70px 150px 290px'

async function load() {
  loading.value = true
  error.value = ''
  try {
    templates.value = await listHyperparameterTemplates()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '模板列表加载失败'
  } finally {
    loading.value = false
  }
}

async function remove(item: HyperparameterTemplate) {
  try {
    await ElMessageBox.confirm(`删除超参数模板“${item.name}”？`, '删除模板', {
      type: 'warning', confirmButtonText: '删除模板', cancelButtonText: '取消',
    })
  } catch {
    return
  }
  deleting.value = item.id
  try {
    await deleteHyperparameterTemplate(item.id)
    templates.value = templates.value.filter((value) => value.id !== item.id)
    ElMessage.success('模板已删除。')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '模板删除失败')
  } finally {
    deleting.value = ''
  }
}

onMounted(load)
</script>

<template>
  <main class="content-page">
    <PageHeader title="超参数模板" kind="hyperparameters">
      <template #meta><span data-test="page-stat">{{ templates.length }} 个模板</span></template>
      <template #actions>
        <VButton variant="primary" @click="router.push('/hyperparameter-templates/new')">
          <template #icon><el-icon><Plus /></el-icon></template>
          新建模板
        </VButton>
      </template>
    </PageHeader>

    <div class="content-body">
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
      <VPanel v-loading="loading" flush>
        <VTable
          :columns="COLUMNS"
          :headers="['模板', 'epochs', 'batch', 'image size', '版本', '编辑时间', '操作']"
        >
          <VRow v-for="item in templates" :key="item.id" :columns="COLUMNS">
            <VCellName :name="item.name" :sub="item.description || '暂无描述'">
              <template #after>
                <VTag v-if="item.system_key" tone="idle">系统</VTag>
              </template>
            </VCellName>
            <span class="vdw-num cell-num">{{ item.epochs }}</span>
            <span class="vdw-num cell-num">
              {{ item.batch_mode === 'auto' ? 'auto' : item.batch_value }}
            </span>
            <span class="vdw-num cell-num">{{ item.image_size }}</span>
            <span class="vdw-num cell-num">v{{ item.version }}</span>
            <time :datetime="item.updated_at">{{ item.updated_at.slice(0, 10) }}</time>
            <div class="row-actions">
              <VButton
                variant="default"
                size="sm"
                @click="router.push(`/hyperparameter-templates/${item.id}`)"
              ><template #icon><el-icon><View /></el-icon></template>详情</VButton>
              <VButton
                v-if="item.can_edit"
                variant="default"
                size="sm"
                @click="router.push(`/hyperparameter-templates/${item.id}/edit`)"
              ><template #icon><el-icon><Edit /></el-icon></template>编辑</VButton>
              <VButton
                variant="quiet"
                size="sm"
                title="以此模板为基础新建"
                @click="router.push(`/hyperparameter-templates/new?from=${item.id}`)"
              >
                <template #icon><el-icon><CopyDocument /></el-icon></template>
                派生
              </VButton>
              <VButton
                v-if="item.can_manage"
                variant="quiet"
                size="sm"
                :loading="deleting === item.id"
                @click="remove(item)"
              >
                <template #icon><el-icon><Delete /></el-icon></template>
                删除
              </VButton>
            </div>
          </VRow>

          <template #empty>
            <VEmpty
              v-if="!loading && !templates.length"
              title="还没有超参数模板"
              note="模板保存 epochs、batch、图像尺寸等训练参数，供训练任务直接引用。"
            >
              <VButton variant="primary" @click="router.push('/hyperparameter-templates/new')">
                新建模板
              </VButton>
            </VEmpty>
          </template>
        </VTable>
      </VPanel>
    </div>
  </main>
</template>

<style scoped>
.cell-num {
  color: var(--vdw-ink);
  font-size: 14px;
}

time {
  color: var(--vdw-ink-2);
  font-size: 14px;
}

/* 行操作左对齐，与其它列同一起点（4.1）。原为 flex-end，操作列孤零零贴右边，
   与左对齐的表头对不上。 */
.row-actions {
  display: flex;
  gap: 2px;
}
</style>
