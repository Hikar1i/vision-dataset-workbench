<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
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
  <main class="content-page model-projects-page">
    <PageHeader title="模型项目">
      <template #meta><span data-test="page-stat">{{ projects.length }} 个项目</span></template>
      <template #actions><el-button type="primary" :icon="Plus" @click="showCreate = !showCreate">{{ showCreate ? '取消新建' : '新建模型项目' }}</el-button></template>
    </PageHeader>
    <div class="content-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <section v-if="showCreate" class="create-panel">
        <header><span>NEW / MODEL PROJECT</span><strong>创建归档模型项目</strong></header>
        <el-form label-position="top" @submit.prevent="create">
          <el-form-item label="项目名称"><el-input v-model="name" maxlength="128" show-word-limit /></el-form-item>
          <el-form-item label="项目类型">
            <el-select model-value="archive" disabled><el-option label="归档" value="archive" /></el-select>
            <p class="field-note">训练项目会在训练任务首次成功后自动同步，不能手工创建。</p>
          </el-form-item>
          <el-form-item label="描述"><el-input v-model="description" type="textarea" :rows="3" maxlength="2000" show-word-limit /></el-form-item>
          <el-form-item label="标签">
            <el-select v-model="tags" multiple filterable allow-create default-first-option style="width:100%" placeholder="选择或输入标签">
              <el-option v-for="tag in availableTags" :key="tag" :label="tag" :value="tag" />
            </el-select>
          </el-form-item>
          <el-button native-type="submit" type="primary" :loading="creating" :disabled="!valid">创建并打开</el-button>
        </el-form>
      </section>
      <section v-loading="loading" class="resource-index">
        <header v-if="projects.length" class="index-row index-header"><span>项目</span><span>标签</span><span>类型</span><span>权限</span><span>创建时间</span><span>更新时间</span><span /></header>
        <article v-for="project in projects" :key="project.id" class="index-row resource-row">
          <div class="resource-identity"><code>{{ project.id.slice(0, 8) }}</code><div><strong>{{ project.name }}</strong><p>{{ project.description || '暂无描述' }}</p></div></div>
          <div class="project-tags"><el-tag v-for="tag in project.tags" :key="tag" size="small" effect="plain">{{ tag }}</el-tag></div>
          <el-tag :type="project.series_type === 'training' ? 'success' : 'info'" effect="plain">{{ project.series_type === 'training' ? '训练' : '归档' }}</el-tag>
          <span>{{ project.can_manage ? '可管理' : '只读' }}</span>
          <time :datetime="project.created_at">{{ project.created_at.slice(0, 10) }}</time>
          <time :datetime="project.updated_at">{{ project.updated_at.slice(0, 10) }}</time>
          <div class="row-actions"><router-link :to="`/model-projects/${project.id}`">打开</router-link><el-button v-if="project.can_manage" type="danger" link :loading="deleting === project.id" @click="remove(project)">删除</el-button></div>
        </article>
        <el-empty v-if="!loading && !projects.length" description="还没有模型项目"><el-button type="primary" @click="showCreate = true">新建模型项目</el-button></el-empty>
      </section>
    </div>
  </main>
</template>

<style scoped>
.model-projects-page { color: #17212b; background: #f4f7fa; }
.create-panel,.resource-index { margin-top: 24px; background: #fff; border: 1px solid #d8dee6; }
.create-panel { display: grid; grid-template-columns: minmax(180px,.55fr) minmax(300px,1fr); gap: 44px; padding: 31px; }
.create-panel header { display: flex; flex-direction: column; gap: 10px; }
.create-panel header span,.resource-identity code { color: #2563eb; font: 12px ui-monospace,SFMono-Regular,Consolas,monospace; letter-spacing: .08em; }
.field-note,.resource-row p { margin: 6px 0 0; color: #687482; font-size: 13px; }
.index-row { display: grid; grid-template-columns: minmax(240px,1fr) minmax(120px,.6fr) 72px 72px 100px 100px 92px; gap: 16px; align-items: center; padding: 17px 22px; border-bottom: 1px solid #e5e9ef; }
.index-header { color: #687482; font-size: 12px; background: #f8fafc; }
.resource-identity { display: flex; gap: 16px; align-items: flex-start; min-width: 0; }
.resource-identity strong { display: block; }
.resource-identity p { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-actions { display: flex; gap: 12px; align-items: center; }
.project-tags { display:flex; gap:6px; flex-wrap:wrap; }
.row-actions a { color: #2563eb; text-decoration: none; }
@media (max-width: 1100px) { .index-row { grid-template-columns: 1fr minmax(120px,.5fr) auto; } .index-row > :nth-child(3),.index-row > :nth-child(4),.index-row > :nth-child(5),.index-row > :nth-child(6),.index-header { display: none; } .create-panel { grid-template-columns: 1fr; } }
</style>
