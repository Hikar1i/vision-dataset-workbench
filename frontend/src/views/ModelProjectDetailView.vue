<script setup lang="ts">
import { Delete, Download, Edit, Plus, Refresh, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import {
  deleteInferenceModel,
  getModelProject,
  listModelProjectModels,
  listModelProjectTags,
  modelDownloadUrl,
  registerInferenceModel,
  updateModelProject,
  type InferenceModel,
  type ModelProject,
} from '../api/models'
import { MODEL_EXTENSIONS } from '../api/filesystem'
import ServerFilePicker from '../components/ServerFilePicker.vue'
import PageHeader from '../components/PageHeader.vue'
import { rememberResource } from '../navigation/recentResources'
import VButton from '../ui/VButton.vue'
import VCellName from '../ui/VCellName.vue'
import VChip from '../ui/VChip.vue'
import VEmpty from '../ui/VEmpty.vue'
import VField from '../ui/VField.vue'
import VPanel from '../ui/VPanel.vue'
import VRow from '../ui/VRow.vue'
import VTable from '../ui/VTable.vue'
import VTag from '../ui/VTag.vue'

const route = useRoute()
const projectId = computed(() => String(route.params.id))
const project = ref<ModelProject>()
const models = ref<InferenceModel[]>([])
const loading = ref(false)
const error = ref('')
const editOpen = ref(false)
const importOpen = ref(false)
const name = ref('')
const description = ref('')
const tags = ref<string[]>([])
const availableTags = ref<string[]>([])
const sourcePath = ref('')
const importName = ref('')
const importDescription = ref('')
const saving = ref(false)
const importing = ref(false)
const readyCount = computed(() => models.value.filter((model) => model.status === 'ready').length)
let loadVersion = 0

const COLUMNS = 'minmax(230px, 1.4fr) 104px 92px 104px 104px 176px'

/** 模型入库状态 → 语气与中文。后端只给英文码。 */
const MODEL_STATUS: Record<string, { tone: 'ok' | 'warn' | 'danger'; label: string }> = {
  ready: { tone: 'ok', label: '可用' },
  failed: { tone: 'danger', label: '入库失败' },
}
const modelStatus = (status: string) =>
  MODEL_STATUS[status] ?? { tone: 'warn' as const, label: '入库中' }

const summary = computed(() => {
  const value = project.value
  if (!value) return []
  return [
    { key: '项目类型', text: value.series_type === 'training' ? '训练' : '归档' },
    { key: '权限', text: value.can_manage ? '可管理' : '只读' },
    { key: '创建时间', text: value.created_at.slice(0, 16).replace('T', ' ') },
    { key: '更新时间', text: value.updated_at.slice(0, 16).replace('T', ' ') },
  ]
})

async function load() {
  const version = ++loadVersion
  const id = projectId.value
  loading.value = true
  error.value = ''
  try {
    const [nextProject, nextModels, nextTags] = await Promise.all([
      getModelProject(id), listModelProjectModels(id), listModelProjectTags(),
    ])
    if (version !== loadVersion) return
    project.value = nextProject
    models.value = nextModels
    availableTags.value = nextTags
    rememberResource('vdm.recent-model-projects', nextProject)
  } catch (reason) {
    if (version !== loadVersion) return
    error.value = reason instanceof Error ? reason.message : '模型项目加载失败'
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

function loadRouteProject() {
  project.value = undefined
  models.value = []
  void load()
}

function openEdit() {
  if (!project.value) return
  name.value = project.value.name
  description.value = project.value.description
  tags.value = [...project.value.tags]
  editOpen.value = true
}

async function saveProject() {
  if (!project.value || !name.value.trim()) return
  saving.value = true
  try {
    project.value = await updateModelProject(
      projectId.value, name.value, description.value, project.value.version, tags.value,
    )
    rememberResource('vdm.recent-model-projects', project.value)
    editOpen.value = false
    ElMessage.success('模型项目信息已更新。')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '模型项目更新失败')
  } finally {
    saving.value = false
  }
}

async function importModel() {
  if (!sourcePath.value || !importName.value.trim()) return
  importing.value = true
  try {
    const registered = await registerInferenceModel(projectId.value, importName.value, sourcePath.value, importDescription.value)
    models.value = [registered.model, ...models.value]
    importOpen.value = false
    sourcePath.value = ''
    importName.value = ''
    importDescription.value = ''
    ElMessage.success('模型导入任务已创建，可在任务中心查看进度。')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '模型导入失败')
  } finally {
    importing.value = false
  }
}

async function removeModel(model: InferenceModel) {
  try {
    await ElMessageBox.confirm(`删除模型“${model.name}”？模型文件将移入 .deleted。`, '删除模型', { type: 'warning', confirmButtonText: '删除模型', cancelButtonText: '取消' })
  } catch { return }
  try {
    await deleteInferenceModel(model.id)
    models.value = models.value.filter((item) => item.id !== model.id)
    ElMessage.success('模型已逻辑删除。')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '模型删除失败')
  }
}

watch(projectId, loadRouteProject, { immediate: true })
</script>

<template>
  <main class="content-page">
    <PageHeader
      :title="project?.name || '加载中'"
      kind="model project"
      :code="project ? project.id.slice(0, 6).toUpperCase() : undefined"
      back-to="/model-projects"
      back-label="返回模型项目"
    >
      <template #meta>
        <span data-test="page-stat">{{ readyCount }} / {{ models.length }} 个可用</span>
      </template>
      <template #actions>
        <VButton :loading="loading" @click="load">
          <template #icon><el-icon><Refresh /></el-icon></template>
          刷新
        </VButton>
        <VButton v-if="project?.can_manage" @click="openEdit">
          <template #icon><el-icon><Edit /></el-icon></template>
          编辑项目
        </VButton>
        <VButton
          v-if="project?.can_manage && project.series_type === 'archive'"
          variant="primary"
          @click="importOpen = true"
        >
          <template #icon><el-icon><Plus /></el-icon></template>
          导入模型
        </VButton>
      </template>
    </PageHeader>

    <div v-loading="loading" class="content-body detail-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <el-alert
        v-if="project?.series_type === 'training'"
        title="训练项目由训练任务同步，不能手工导入或移动模型。"
        type="info"
        :closable="false"
        show-icon
      />
      <el-alert
        v-if="project?.system_key"
        title="临时模型项目为历史兼容资源，已设为只读。"
        type="warning"
        :closable="false"
        show-icon
      />

      <VPanel v-if="project" title="项目信息">
        <dl class="fact-grid">
          <div v-for="item in summary" :key="item.key">
            <dt>{{ item.key }}</dt>
            <dd>{{ item.text }}</dd>
          </div>
          <div class="fact-grid__wide">
            <dt>标签</dt>
            <dd class="fact-tags">
              <VChip v-for="tag in project.tags" :key="tag">{{ tag }}</VChip>
            </dd>
          </div>
          <div class="fact-grid__wide">
            <dt>描述</dt>
            <dd>{{ project.description || '暂无项目描述' }}</dd>
          </div>
        </dl>
      </VPanel>

      <VPanel flush>
        <VTable
          :columns="COLUMNS"
          :headers="['模型', '状态', '文件', '添加时间', '更新时间', '操作']"
        >
          <VRow v-for="model in models" :key="model.id" :columns="COLUMNS">
            <VCellName :name="model.name">
              <template #sub>
                <span class="model-code">{{ model.model_code }}</span>
              </template>
            </VCellName>
            <VTag :tone="modelStatus(model.status).tone">
              {{ modelStatus(model.status).label }}
            </VTag>
            <span class="vdw-num cell-num">
              {{ model.file_size == null ? '—' : `${(model.file_size / 1024 / 1024).toFixed(1)} MB` }}
            </span>
            <time>{{ model.created_at.slice(0, 10) }}</time>
            <time>{{ model.updated_at.slice(0, 10) }}</time>
            <div class="row-actions">
              <VButton
                variant="default"
                size="sm"
                @click="$router.push(`/model-projects/${projectId}/models/${model.id}`)"
              ><template #icon><el-icon><View /></el-icon></template>详情</VButton>
              <VButton
                v-if="model.status === 'ready'"
                variant="quiet"
                size="sm"
                :href="modelDownloadUrl(model.id)"
              ><template #icon><el-icon><Download /></el-icon></template>下载</VButton>
              <VButton
                v-if="model.can_manage"
                variant="danger"
                size="sm"
                @click="removeModel(model)"
              ><template #icon><el-icon><Delete /></el-icon></template>删除</VButton>
            </div>
          </VRow>

          <template #empty>
            <VEmpty
              v-if="!loading && !models.length"
              title="该项目还没有模型"
              :note="project?.series_type === 'training'
                ? '训练任务成功后，产出模型会自动同步到这里。'
                : '导入 .pt 权重文件后即可用于自动标注。'"
            >
              <VButton
                v-if="project?.can_manage && project.series_type === 'archive'"
                variant="primary"
                @click="importOpen = true"
              >导入模型</VButton>
            </VEmpty>
          </template>
        </VTable>
      </VPanel>
    </div>

    <el-dialog v-model="editOpen" title="编辑模型项目" width="560px">
      <div class="dialog-form">
        <VField label="项目名称" required>
          <template #default="{ id }">
            <el-input :id="id" v-model="name" maxlength="128" />
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
            >
              <el-option v-for="tag in availableTags" :key="tag" :label="tag" :value="tag" />
            </el-select>
          </template>
        </VField>
        <VField label="描述">
          <template #default="{ id }">
            <el-input :id="id" v-model="description" type="textarea" :rows="4" maxlength="2000" />
          </template>
        </VField>
      </div>
      <template #footer>
        <VButton variant="quiet" @click="editOpen = false">取消</VButton>
        <VButton
          variant="primary"
          :loading="saving"
          :disabled="!name.trim() || !tags.length"
          @click="saveProject"
        >保存更改</VButton>
      </template>
    </el-dialog>

    <el-dialog
      v-model="importOpen"
      title="导入 YOLO 模型"
      top="3vh"
      width="min(1040px, calc(100vw - 32px))"
    >
      <div class="dialog-form">
        <VField label="模型名称" required>
          <template #default="{ id }">
            <el-input :id="id" v-model="importName" maxlength="128" />
          </template>
        </VField>
        <VField label="模型描述">
          <template #default="{ id }">
            <el-input
              :id="id"
              v-model="importDescription"
              type="textarea"
              :rows="2"
              maxlength="2000"
            />
          </template>
        </VField>
        <VField label=".pt 文件" required>
          <template #default>
            <ServerFilePicker
              v-model="sourcePath"
              mode="single-file"
              :allowed-extensions="MODEL_EXTENSIONS"
            />
          </template>
        </VField>
      </div>
      <template #footer>
        <VButton variant="quiet" @click="importOpen = false">取消</VButton>
        <VButton
          variant="primary"
          :loading="importing"
          :disabled="!importName.trim() || !sourcePath"
          @click="importModel"
        >创建导入任务</VButton>
      </template>
    </el-dialog>
  </main>
</template>

<style scoped>
.detail-body {
  display: grid;
  align-content: start;
  gap: 14px;
}

.fact-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px 20px;
  margin: 0;
}

.fact-grid__wide {
  grid-column: 1 / -1;
}

.fact-grid dt {
  color: var(--vdw-ink-3);
  font-size: 13px;
}

.fact-grid dd {
  margin: 5px 0 0;
  font-size: 14px;
}

.fact-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.model-code {
  font-family: var(--vdw-mono);
}

.cell-num,
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

.dialog-form {
  display: grid;
  gap: 16px;
}

.dialog-form :deep(.el-select),
.dialog-form :deep(.el-input) {
  width: 100%;
}
</style>
