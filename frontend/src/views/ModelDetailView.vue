<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  getInferenceModel,
  listModelProjects,
  modelDownloadUrl,
  updateInferenceModel,
  type InferenceModel,
  type ModelProject,
} from '../api/models'
import PageHeader from '../components/PageHeader.vue'
import VButton from '../ui/VButton.vue'
import VField from '../ui/VField.vue'
import VPanel from '../ui/VPanel.vue'
import VTag from '../ui/VTag.vue'

const route = useRoute()
const modelId = String(route.params.modelId)
const model = ref<InferenceModel>()
const projects = ref<ModelProject[]>([])
const editing = ref(false)
const saving = ref(false)
const error = ref('')
const name = ref('')
const description = ref('')
const targetProjectId = ref('')

const movableProjects = computed(() =>
  projects.value.filter(
    (item) => item.series_type === 'archive' && item.can_manage && !item.system_key,
  ),
)

/** 模型可用状态 → 语气。后端只给英文码，页面必须给出中文与语气。 */
const STATUS: Record<string, { tone: 'ok' | 'warn' | 'danger' | 'idle'; label: string }> = {
  ready: { tone: 'ok', label: '可用' },
  importing: { tone: 'warn', label: '入库中' },
  failed: { tone: 'danger', label: '入库失败' },
  missing: { tone: 'danger', label: '文件缺失' },
}
const status = computed(() => {
  const value = model.value?.status
  if (!value) return { tone: 'idle' as const, label: '—' }
  return STATUS[value] ?? { tone: 'idle' as const, label: value }
})

const facts = computed(() => {
  const value = model.value
  if (!value) return []
  return [
    { key: '模型 code', text: value.model_code, mono: true },
    { key: '来源文件', text: value.source_name },
    {
      key: '文件大小',
      text: value.file_size == null
        ? '—'
        : `${(value.file_size / 1024 / 1024).toFixed(2)} MB`,
      mono: true,
    },
    { key: '创建时间', text: value.created_at.slice(0, 16).replace('T', ' '), mono: true },
    { key: '更新时间', text: value.updated_at.slice(0, 16).replace('T', ' '), mono: true },
    { key: 'SHA-256', text: value.sha256 || '—', mono: true, wrap: true },
    { key: '存储路径', text: value.storage_path || '—', mono: true, wrap: true },
  ]
})

async function load() {
  try {
    ;[model.value, projects.value] = await Promise.all([
      getInferenceModel(modelId),
      listModelProjects(),
    ])
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '模型详情加载失败'
  }
}

function edit() {
  if (!model.value) return
  name.value = model.value.name
  description.value = model.value.description
  targetProjectId.value = model.value.model_project_id
  editing.value = true
}

async function save() {
  if (!model.value || !name.value.trim()) return
  saving.value = true
  try {
    model.value = await updateInferenceModel(
      modelId, name.value, description.value, model.value.version, targetProjectId.value,
    )
    editing.value = false
    ElMessage.success('模型信息已更新。')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '模型更新失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="content-page">
    <PageHeader
      :title="model?.name || '模型详情'"
      kind="model"
      :code="model?.model_code"
      :back-to="`/model-projects/${route.params.id}`"
      back-label="返回模型列表"
    >
      <template v-if="model" #eyebrow>
        <VTag :tone="status.tone">{{ status.label }}</VTag>
      </template>
      <template #actions>
        <VButton
          v-if="model?.status === 'ready'"
          :href="modelDownloadUrl(model.id)"
        >下载模型</VButton>
        <VButton v-if="model?.can_manage" variant="primary" @click="edit">编辑模型</VButton>
      </template>
    </PageHeader>

    <div class="content-body detail-body">
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

      <template v-if="model">
        <VPanel title="模型信息">
          <dl class="fact-grid">
            <div v-for="fact in facts" :key="fact.key">
              <dt>{{ fact.key }}</dt>
              <dd :class="{ 'is-mono': fact.mono, 'is-wrap': fact.wrap }">{{ fact.text }}</dd>
            </div>
          </dl>
        </VPanel>

        <VPanel title="描述">
          <p class="model-description">{{ model.description || '暂无描述' }}</p>
        </VPanel>

        <VPanel title="参数信息" flush>
          <pre class="model-parameters">{{ JSON.stringify(model.parameters, null, 2) }}</pre>
        </VPanel>
      </template>
    </div>

    <el-dialog v-model="editing" title="编辑模型" width="560px">
      <div class="model-form">
        <VField label="模型名称" required>
          <template #default="{ id }">
            <el-input :id="id" v-model="name" maxlength="128" />
          </template>
        </VField>
        <VField label="所属归档项目">
          <template #default="{ id }">
            <el-select :id="id" v-model="targetProjectId">
              <el-option
                v-for="project in movableProjects"
                :key="project.id"
                :label="project.name"
                :value="project.id"
              />
            </el-select>
          </template>
        </VField>
        <VField label="描述">
          <template #default="{ id }">
            <el-input :id="id" v-model="description" type="textarea" :rows="3" maxlength="2000" />
          </template>
        </VField>
      </div>
      <template #footer>
        <VButton variant="quiet" @click="editing = false">取消</VButton>
        <VButton variant="primary" :loading="saving" :disabled="!name.trim()" @click="save">
          保存更改
        </VButton>
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
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px 20px;
  margin: 0;
}

.fact-grid dt {
  color: var(--vdw-ink-3);
  font-size: 13px;
}

.fact-grid dd {
  margin: 5px 0 0;
  font-size: 14px;
}

.fact-grid dd.is-mono {
  font-family: var(--vdw-mono);
}

.fact-grid dd.is-wrap {
  overflow-wrap: anywhere;
}

.model-description {
  margin: 0;
  color: var(--vdw-ink-2);
  line-height: 1.6;
}

.model-parameters {
  max-height: 360px;
  margin: 0;
  padding: 16px;
  overflow: auto;
  color: var(--vdw-focus-ink);
  font: 13px/1.6 var(--vdw-mono);
  background: var(--vdw-focus-canvas);
  border-radius: 0 0 var(--vdw-radius-card) var(--vdw-radius-card);
}

.model-form {
  display: grid;
  gap: 16px;
}

.model-form :deep(.el-select),
.model-form :deep(.el-input) {
  width: 100%;
}
</style>
