<script setup lang="ts">
import { Delete, Right } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'

import { ApiError } from '../api/auth'
import { createProject, deleteProject, listProjects, type Project } from '../api/projects'
import PageHeader from '../components/PageHeader.vue'
import VButton from '../ui/VButton.vue'
import VCellName from '../ui/VCellName.vue'
import VChip from '../ui/VChip.vue'
import VEmpty from '../ui/VEmpty.vue'
import VField from '../ui/VField.vue'
import VPanel from '../ui/VPanel.vue'
import { isRecentRow, markRecentRowFromAction } from '../ui/recentRows'
import VRow from '../ui/VRow.vue'
import VTable from '../ui/VTable.vue'
import VTag from '../ui/VTag.vue'

const emit = defineEmits<{ 'project-deleted': [id: string] }>()
const router = useRouter()
const projects = ref<Project[]>([])
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const loading = ref(false)
const showCreate = ref(false)
const name = ref('')
const description = ref('')
const creating = ref(false)
const deleting = ref('')
const error = ref('')
const valid = computed(() => name.value.trim().length > 0 && name.value.trim().length <= 128)

const roleLabels = { owner: '所有者', editor: '编辑者', viewer: '只读' } as const

const COLUMNS = 'minmax(260px, 2fr) 96px minmax(120px, 0.7fr) 116px 150px'
const RECENT_SCOPE = 'projects'

async function load(nextPage = page.value) {
  loading.value = true
  error.value = ''
  try {
    const result = await listProjects(nextPage)
    projects.value = result.items
    page.value = result.page
    pageSize.value = result.page_size
    total.value = result.total
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '项目列表加载失败'
  } finally {
    loading.value = false
  }
}

async function create() {
  if (!valid.value) return
  creating.value = true
  error.value = ''
  try {
    const project = await createProject(name.value, description.value)
    await router.push(`/projects/${project.id}/videos`)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '项目创建失败'
  } finally {
    creating.value = false
  }
}

async function remove(project: Project) {
  try {
    await ElMessageBox.confirm(
      `删除数据集项目“${project.name}”？项目目录和完整元数据将移入工作区 .deleted 目录，项目随后不再显示。`,
      '删除数据集项目',
      {
        type: 'warning',
        confirmButtonText: '删除项目',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return
  }
  deleting.value = project.id
  try {
    await deleteProject(project.id)
    emit('project-deleted', project.id)
    ElMessage.success('项目已归档至逻辑删除目录。')
    await load(page.value > 1 && projects.value.length === 1 ? page.value - 1 : page.value)
  } catch (reason) {
    ElMessage.error(
      reason instanceof ApiError && reason.status === 409
        ? '项目仍有排队中或运行中任务，请先处理任务。'
        : reason instanceof Error ? reason.message : '项目删除失败',
    )
  } finally {
    deleting.value = ''
  }
}

onMounted(() => load())
</script>

<template>
  <main class="content-page">
    <PageHeader title="数据集项目" kind="projects">
      <template #meta><span data-test="page-stat">{{ total }} 个项目</span></template>
      <template #actions>
        <VButton
          :variant="showCreate ? 'default' : 'primary'"
          data-test="show-create"
          @click="showCreate = !showCreate"
        >{{ showCreate ? '取消新建' : '新建项目' }}</VButton>
      </template>
    </PageHeader>

    <div class="content-body projects-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

      <Transition name="vdw-expand">
        <div v-if="showCreate">
          <VPanel title="创建视频项目">
            <form class="create-form" @submit.prevent="create">
              <VField label="项目名称" required>
                <template #default="{ id }">
                  <el-input
                    :id="id"
                    v-model="name"
                    data-test="project-name"
                    maxlength="128"
                    show-word-limit
                    autofocus
                  />
                </template>
              </VField>
              <VField label="描述">
                <template #default="{ id }">
                  <el-input
                    :id="id"
                    v-model="description"
                    data-test="project-description"
                    type="textarea"
                    :rows="3"
                    maxlength="2000"
                    show-word-limit
                  />
                </template>
              </VField>
              <div class="create-form__actions">
                <VButton variant="primary" type="submit" :loading="creating" :disabled="!valid">
                  创建并打开
                </VButton>
              </div>
            </form>
          </VPanel>
        </div>
      </Transition>

      <VPanel v-loading="loading" flush>
        <VTable
          :columns="COLUMNS"
          :headers="['项目', '权限', '所有者', '最近更新', '操作']"
        >
          <VRow
            v-for="project in projects"
            :key="project.id"
            :columns="COLUMNS"
            :recent="isRecentRow(RECENT_SCOPE, project.id)"
          >
            <VCellName :name="project.name" :sub="project.description || '暂无描述'">
              <template #badge>
                <VChip variant="id">{{ project.id.slice(0, 6).toUpperCase() }}</VChip>
              </template>
            </VCellName>
            <VTag :tone="project.role === 'owner' ? 'run' : 'idle'">
              {{ roleLabels[project.role] }}
            </VTag>
            <span class="cell-muted">{{ project.creator_username }}</span>
            <time :datetime="project.updated_at">{{ project.updated_at.slice(0, 10) }}</time>
            <div
              class="row-actions"
              @click.capture="markRecentRowFromAction($event, RECENT_SCOPE, project.id)"
            >
              <VButton
                variant="default"
                size="sm"
                :data-test="`open-${project.id}`"
                @click="router.push(`/projects/${project.id}/videos`)"
              ><template #icon><el-icon><Right /></el-icon></template>打开</VButton>
              <VButton
                v-if="project.role === 'owner'"
                variant="danger"
                size="sm"
                :data-test="`delete-${project.id}`"
                :loading="deleting === project.id"
                :disabled="Boolean(deleting)"
                @click="remove(project)"
              ><template #icon><el-icon><Delete /></el-icon></template>删除</VButton>
            </div>
          </VRow>

          <template #empty>
            <VEmpty
              v-if="!loading && !projects.length"
              title="还没有项目"
              note="创建第一个视频项目，随后可添加协作者和导入媒体。"
            >
              <VButton variant="primary" @click="showCreate = true">新建项目</VButton>
            </VEmpty>
          </template>
        </VTable>
      </VPanel>

      <el-pagination
        v-if="total > pageSize"
        layout="prev, pager, next"
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        @current-change="load"
      />
    </div>
  </main>
</template>

<style scoped>
.projects-body {
  display: grid;
  align-content: start;
  gap: 14px;
}

.create-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 18px;
}

.create-form :deep(.el-input),
.create-form :deep(.el-textarea) {
  width: 100%;
}

.create-form__actions {
  display: flex;
  grid-column: 1 / -1;
  justify-content: flex-end;
}

.cell-muted,
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

.el-pagination {
  justify-content: flex-end;
}
</style>
