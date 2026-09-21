<script setup lang="ts">
import { CopyDocument, Edit } from '@element-plus/icons-vue'
import { stringify } from 'yaml'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getHyperparameterTemplate, type HyperparameterTemplate } from '../api/hyperparameters'
import { accessLabel } from '../api/access'
import { getModelProject, type ModelProject } from '../api/models'
import ModelProjectMembersPanel from '../components/ModelProjectMembersPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import VButton from '../ui/VButton.vue'
import VChip from '../ui/VChip.vue'
import { formatDateTime } from '../ui/dateTime'
import VPanel from '../ui/VPanel.vue'

const route = useRoute()
const router = useRouter()
const item = ref<HyperparameterTemplate>()
const project = ref<ModelProject>()
const error = ref('')
const raw = computed(() => item.value ? stringify(item.value.effective_parameters, { lineWidth: 0 }) : '')

onMounted(async () => {
  try {
    item.value = await getHyperparameterTemplate(String(route.params.id))
    if (item.value.model_project_id) {
      project.value = await getModelProject(item.value.model_project_id)
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '模板详情加载失败'
  }
})
</script>

<template>
  <main class="content-page detail-page">
    <PageHeader
      :title="item?.name || '模板详情'"
      kind="hyperparameters"
      :code="item?.id?.slice(0, 6).toUpperCase()"
      back-to="/hyperparameter-templates"
      back-label="返回超参数模板"
    >
      <template v-if="item" #eyebrow>
        <VChip>{{ item.system_key ? '系统模板' : '自定义模板' }}</VChip>
        <VChip>v{{ item.version }}</VChip>
      </template>
      <template v-if="item" #meta>
        epochs {{ item.epochs }} · image size {{ item.image_size }} · batch
        {{ item.batch_mode === 'auto' ? 'auto' : item.batch_value }} · 编辑于
        {{ formatDateTime(item.updated_at) }}
      </template>
      <template #actions>
        <VButton
          v-if="item?.can_edit"
          variant="default"
          @click="router.push(`/hyperparameter-templates/${item.id}/edit`)"
        >
          <template #icon><el-icon><Edit /></el-icon></template>
          编辑模板
        </VButton>
        <VButton
          v-if="item"
          variant="primary"
          @click="router.push(`/hyperparameter-templates/new?from=${item.id}`)"
        >
          <template #icon><el-icon><CopyDocument /></el-icon></template>
          派生模板
        </VButton>
      </template>
    </PageHeader>
    <div class="content-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <section v-if="item" class="detail-grid">
        <div><span>epochs</span><strong>{{ item.epochs }}</strong></div>
        <div>
          <span>batch size</span>
          <strong>{{ item.batch_mode === 'auto' ? 'auto' : item.batch_value }}</strong>
        </div>
        <div><span>image size</span><strong>{{ item.image_size }}</strong></div>
        <div><span>版本</span><strong>v{{ item.version }}</strong></div>
        <div><span>目录版本</span><code>{{ item.catalog_version }}</code></div>
        <div><span>创建时间</span><time>{{ formatDateTime(item.created_at) }}</time></div>
        <div><span>编辑时间</span><time>{{ formatDateTime(item.updated_at) }}</time></div>
        <article><span>描述</span><p>{{ item.description || '暂无描述' }}</p></article>
        <article><span>RAW 配置</span><pre>{{ raw }}</pre></article>
      </section>
      <VPanel v-if="item?.system_key" title="权限归属">
        <el-alert
          title="系统模板由系统维护，所有正常账号均可读取，不支持单独授权。"
          type="info"
          :closable="false"
          show-icon
        />
      </VPanel>
      <template v-else-if="project">
        <VPanel title="权限归属">
          <dl class="project-access">
            <div><dt>所属模型项目</dt><dd><RouterLink :to="`/model-projects/${project.id}`">{{ project.name }}</RouterLink></dd></div>
            <div><dt>项目编号</dt><dd><code>{{ project.id.slice(0, 6).toUpperCase() }}</code></dd></div>
            <div><dt>当前权限</dt><dd>{{ accessLabel(project.access) }}</dd></div>
          </dl>
        </VPanel>
        <ModelProjectMembersPanel
          :project="project"
          scope-description="成员授权作用于模板所属的整个模型项目，不只作用于当前模板。"
        />
      </template>
    </div>
  </main>
</template>

<style scoped>
.detail-page { background: var(--vdw-app); }
.content-body { display: grid; gap: 14px; }
.detail-grid { margin-top: 24px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; background: var(--vdw-line); border: 1px solid var(--vdw-line); border-radius: var(--vdw-radius-card); overflow: hidden; }
.detail-grid > * { padding: 20px; background: var(--vdw-surface); }
.detail-grid span { display: block; margin-bottom: 7px; color: var(--vdw-ink-2); font-size: 14px; }
.detail-grid article { grid-column: 1 / -1; }
.detail-grid p { margin: 0; }
.detail-grid pre { margin: 0; padding: 18px; background: var(--vdw-focus-canvas); color: var(--vdw-focus-ink); overflow: auto; }
.project-access { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin: 0; }
.project-access dt { color: var(--vdw-ink-3); font-size: 13px; }
.project-access dd { margin: 5px 0 0; }
</style>
