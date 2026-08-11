<script setup lang="ts">
import { Delete, Plus, Right } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  createModelProject,
  deleteModelProject,
  listModelProjects,
  listModelProjectTags,
  type ModelProject,
} from '../api/models'
import { forgetResource } from '../navigation/recentResources'
import PageHeader from '../components/PageHeader.vue'
import VButton from '../ui/VButton.vue'
import VCellName from '../ui/VCellName.vue'
import VChip from '../ui/VChip.vue'
import VEmpty from '../ui/VEmpty.vue'
import VField from '../ui/VField.vue'
import VPanel from '../ui/VPanel.vue'
import VRow from '../ui/VRow.vue'
import VTable from '../ui/VTable.vue'
import VTag from '../ui/VTag.vue'

const router = useRouter()
const projects = ref<ModelProject[]>([])
const loading = ref(false)
const creating = ref(false)
const deleting = ref('')
const showCreate = ref(false)
const name = ref('')
const description = ref('')
const tags = ref<string[]>(['未分类'])
const availableTags = ref<string[]>([])
const error = ref('')

const COLUMNS =
  'minmax(240px, 1.4fr) minmax(130px, 0.7fr) 92px 84px 106px 106px 132px'

const valid = computed(() =>
  name.value.trim().length > 0 && name.value.trim().length <= 128 && tags.value.length > 0,
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    ;[projects.value, availableTags.value] = await Promise.all([
      listModelProjects(),
      listModelProjectTags(),
    ])
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '模型项目列表加载失败'
  } finally {
    loading.value = false
  }
}

async function create() {
  if (!valid.value) return
  creating.value = true
  try {
    const project = await createModelProject(name.value, description.value, tags.value)
    await router.push(`/model-projects/${project.id}`)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '模型项目创建失败'
  } finally {
    creating.value = false
  }
}

async function remove(project: ModelProject) {
  try {
    await ElMessageBox.confirm(
      `删除模型项目“${project.name}”？项目中的模型文件将移入工作区 .deleted 目录。`,
      '删除模型项目',
      { type: 'warning', confirmButtonText: '删除项目', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  deleting.value = project.id
  try {
    await deleteModelProject(project.id)
    forgetResource('vdm.recent-model-projects', project.id)
    ElMessage.success('模型项目已逻辑删除。')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '模型项目删除失败')
  } finally {
    deleting.value = ''
  }
}

onMounted(load)
</script>

<template>
  <main class="content-page">
    <PageHeader title="模型项目" kind="model projects">
      <template #meta><span data-test="page-stat">{{ projects.length }} 个项目</span></template>
      <template #actions>
        <VButton
          :variant="showCreate ? 'default' : 'primary'"
          @click="showCreate = !showCreate"
        >
          <template v-if="!showCreate" #icon><el-icon><Plus /></el-icon></template>
          {{ showCreate ? '取消新建' : '新建模型项目' }}
        </VButton>
      </template>
    </PageHeader>

    <div class="content-body model-projects-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

      <Transition name="vdw-expand">
        <div v-if="showCreate">
          <VPanel title="创建归档模型项目">
            <form class="create-form" @submit.prevent="create">
              <VField label="项目名称" required>
                <template #default="{ id }">
                  <el-input :id="id" v-model="name" maxlength="128" show-word-limit />
                </template>
              </VField>
              <VField
                label="项目类型"
                note="训练项目会在训练任务首次成功后自动同步，不能手工创建。"
              >
                <template #default="{ id }">
                  <el-select :id="id" model-value="archive" disabled>
                    <el-option label="归档" value="archive" />
                  </el-select>
                </template>
              </VField>
              <VField label="标签" required>
                <template #default="{ id }">
                  <el-select
                    :id="id"
                    v-model="tags"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    placeholder="选择或输入标签"
                  >
                    <el-option v-for="tag in availableTags" :key="tag" :label="tag" :value="tag" />
                  </el-select>
                </template>
              </VField>
              <VField label="描述" class="create-form__wide">
                <template #default="{ id }">
                  <el-input
                    :id="id"
                    v-model="description"
                    type="textarea"
                    :rows="3"
                    maxlength="2000"
                    show-word-limit
                  />
                </template>
              </VField>
              <div class="create-form__actions">
                <VButton type="submit" variant="primary" :loading="creating" :disabled="!valid">
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
          :headers="['项目', '标签', '类型', '权限', '创建时间', '更新时间', '操作']"
        >
          <VRow v-for="project in projects" :key="project.id" :columns="COLUMNS">
            <VCellName :name="project.name" :sub="project.description || '暂无描述'">
              <template #badge>
                <VChip variant="id">{{ project.id.slice(0, 6).toUpperCase() }}</VChip>
              </template>
            </VCellName>
            <div class="project-tags">
              <VChip v-for="tag in project.tags" :key="tag">{{ tag }}</VChip>
            </div>
            <VTag :tone="project.series_type === 'training' ? 'run' : 'idle'">
              {{ project.series_type === 'training' ? '训练' : '归档' }}
            </VTag>
            <span class="cell-muted">{{ project.can_manage ? '可管理' : '只读' }}</span>
            <time :datetime="project.created_at">{{ project.created_at.slice(0, 10) }}</time>
            <time :datetime="project.updated_at">{{ project.updated_at.slice(0, 10) }}</time>
            <div class="row-actions">
              <VButton
                variant="default"
                size="sm"
                @click="router.push(`/model-projects/${project.id}`)"
              ><template #icon><el-icon><Right /></el-icon></template>打开</VButton>
              <VButton
                v-if="project.can_manage"
                variant="danger"
                size="sm"
                :loading="deleting === project.id"
                @click="remove(project)"
              ><template #icon><el-icon><Delete /></el-icon></template>删除</VButton>
            </div>
          </VRow>

          <template #empty>
            <VEmpty
              v-if="!loading && !projects.length"
              title="还没有模型项目"
              note="归档模型项目用于收纳外部导入的权重；训练产出的项目会自动出现在这里。"
            >
              <VButton variant="primary" @click="showCreate = true">新建模型项目</VButton>
            </VEmpty>
          </template>
        </VTable>
      </VPanel>
    </div>
  </main>
</template>

<style scoped>
.model-projects-body {
  display: grid;
  align-content: start;
  gap: 14px;
}

.create-form {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px 18px;
}

.create-form__wide {
  grid-column: 1 / -1;
}

.create-form :deep(.el-select),
.create-form :deep(.el-input) {
  width: 100%;
}

.create-form__actions {
  display: flex;
  grid-column: 1 / -1;
  justify-content: flex-end;
  padding-top: 4px;
}

.project-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  min-width: 0;
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
</style>
