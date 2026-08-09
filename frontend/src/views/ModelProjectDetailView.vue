<script setup lang="ts">
import { Edit, Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

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
import { rememberResource } from '../navigation/recentResources'

const route = useRoute()
const router = useRouter()
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
  <main class="content-page model-detail-page">
    <header class="content-toolbar">
      <div class="content-toolbar-title"><el-button link @click="router.push('/model-projects')">模型项目 /</el-button><h1>{{ project?.name || '加载中' }}</h1><span>{{ readyCount }} / {{ models.length }} 个可用</span></div>
      <div class="toolbar-actions"><el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button><el-button v-if="project?.can_manage" :icon="Edit" @click="openEdit">编辑项目</el-button><el-button v-if="project?.can_manage && project.series_type === 'archive'" type="primary" :icon="Plus" @click="importOpen = true">导入模型</el-button></div>
    </header>
    <div v-loading="loading" class="content-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <section v-if="project" class="project-summary">
        <div><span>项目类型</span><strong>{{ project.series_type === 'training' ? '训练' : '归档' }}</strong></div>
        <div><span>权限</span><strong>{{ project.can_manage ? '可管理' : '只读' }}</strong></div>
        <div><span>创建时间</span><strong>{{ project.created_at.slice(0, 16).replace('T', ' ') }}</strong></div>
        <div><span>更新时间</span><strong>{{ project.updated_at.slice(0, 16).replace('T', ' ') }}</strong></div>
        <div class="summary-tags"><span>标签</span><p><el-tag v-for="tag in project.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag></p></div>
        <p class="summary-description">{{ project.description || '暂无项目描述' }}</p>
      </section>
      <el-alert v-if="project?.series_type === 'training'" title="训练项目由训练任务同步，不能手工导入或移动模型。" type="info" :closable="false" show-icon />
      <el-alert v-if="project?.system_key" title="临时模型项目为历史兼容资源，已设为只读。" type="warning" :closable="false" show-icon />
      <section class="model-table">
        <header class="model-row"><span>模型</span><span>状态</span><span>文件</span><span>添加时间</span><span>更新时间</span><span /></header>
        <article v-for="model in models" :key="model.id" class="model-row">
          <div><strong>{{ model.name }}</strong><code>{{ model.model_code }}</code><p>{{ model.description || '暂无描述' }}</p></div>
          <el-tag :type="model.status === 'ready' ? 'success' : model.status === 'failed' ? 'danger' : 'warning'" effect="plain">{{ model.status === 'ready' ? '可用' : model.status === 'failed' ? '失败' : '导入中' }}</el-tag>
          <span>{{ model.file_size == null ? '—' : `${(model.file_size / 1024 / 1024).toFixed(1)} MB` }}</span>
          <time>{{ model.created_at.slice(0, 10) }}</time>
          <time>{{ model.updated_at.slice(0, 10) }}</time>
          <div><router-link :to="`/model-projects/${projectId}/models/${model.id}`">详情</router-link><a v-if="model.status === 'ready'" :href="modelDownloadUrl(model.id)">下载</a><el-button v-if="model.can_manage" type="danger" link @click="removeModel(model)">删除</el-button></div>
        </article>
        <el-empty v-if="!loading && !models.length" description="该项目还没有模型" />
      </section>
    </div>
    <el-dialog v-model="editOpen" title="编辑模型项目" width="520px"><el-form label-position="top"><el-form-item label="项目名称"><el-input v-model="name" maxlength="128" /></el-form-item><el-form-item label="标签"><el-select v-model="tags" multiple filterable allow-create default-first-option style="width:100%"><el-option v-for="tag in availableTags" :key="tag" :label="tag" :value="tag" /></el-select></el-form-item><el-form-item label="描述"><el-input v-model="description" type="textarea" :rows="4" maxlength="2000" /></el-form-item></el-form><template #footer><el-button @click="editOpen = false">取消</el-button><el-button type="primary" :loading="saving" :disabled="!name.trim() || !tags.length" @click="saveProject">保存更改</el-button></template></el-dialog>
    <el-dialog v-model="importOpen" title="导入 YOLO 模型" width="min(1040px, calc(100vw - 32px))"><el-form label-position="top"><el-form-item label="模型名称"><el-input v-model="importName" maxlength="128" /></el-form-item><el-form-item label="模型描述"><el-input v-model="importDescription" type="textarea" :rows="2" maxlength="2000" /></el-form-item><el-form-item label=".pt 文件"><ServerFilePicker v-model="sourcePath" mode="single-file" :allowed-extensions="MODEL_EXTENSIONS" /></el-form-item></el-form><template #footer><el-button @click="importOpen = false">取消</el-button><el-button type="primary" :loading="importing" :disabled="!importName.trim() || !sourcePath" @click="importModel">创建导入任务</el-button></template></el-dialog>
  </main>
</template>

<style scoped>
.model-detail-page { background:#f4f7fa; color:#17212b; }.toolbar-actions,.model-row>div:last-child { display:flex; gap:10px; align-items:center; }.project-summary { margin:24px 0 16px; padding:22px; display:grid; grid-template-columns:repeat(4,minmax(120px,1fr)); gap:20px; background:#fff; border:1px solid #d8dee6; }.project-summary div { display:flex; flex-direction:column; gap:5px; }.project-summary span { color:#687482; font-size:12px; }.project-summary p { margin:0; }.summary-tags,.summary-description{grid-column:1/-1}.summary-tags p{display:flex;gap:6px;flex-wrap:wrap}.model-table { margin-top:16px; background:#fff; border:1px solid #d8dee6; }.model-row { display:grid; grid-template-columns:minmax(230px,1fr) 78px 84px 96px 96px 146px; gap:14px; align-items:center; padding:16px 20px; border-bottom:1px solid #e5e9ef; }.model-row>div:first-child { min-width:0; }.model-row code { display:block; margin-top:4px; color:#2563eb; }.model-row p { margin:4px 0 0; color:#687482; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.model-row a { color:#2563eb; text-decoration:none; }.model-table>header { color:#687482; font-size:12px; background:#f8fafc; }@media(max-width:1000px){.model-row{grid-template-columns:1fr auto}.model-row>:nth-child(3),.model-row>:nth-child(4),.model-row>:nth-child(5),.model-table>header{display:none}.project-summary{grid-template-columns:1fr 1fr}.project-summary p{grid-column:1/-1}}
</style>
