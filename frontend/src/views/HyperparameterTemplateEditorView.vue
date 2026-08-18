<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  createHyperparameterTemplate,
  getHyperparameterCatalog,
  getHyperparameterTemplate,
  updateHyperparameterTemplate,
  type HyperparameterConfig,
  type HyperparameterTemplate,
  type ParameterDefinition,
} from '../api/hyperparameters'
import HyperparameterConfigEditor from '../components/HyperparameterConfigEditor.vue'
import PageHeader from '../components/PageHeader.vue'
import VButton from '../ui/VButton.vue'

const route = useRoute()
const router = useRouter()
const catalog = ref<ParameterDefinition[]>([])
const source = ref<HyperparameterTemplate | null>(null)
const name = ref('')
const description = ref('')
const config = ref<HyperparameterConfig>({
  epochs: 100,
  batch_mode: 'auto',
  batch_value: null,
  image_size: 640,
  extra_parameters: {},
})
const rawDirty = ref(false)
const saving = ref(false)
const derivedFromId = ref<string | null>(null)
const editorKey = ref(0)
const editing = computed(() => route.name === 'hyperparameter-template-edit')
const title = computed(() => editing.value ? '编辑超参数模板' : derivedFromId.value ? '派生超参数模板' : '新建超参数模板')

function defaultConfig(): HyperparameterConfig {
  return { epochs: 100, batch_mode: 'auto', batch_value: null, image_size: 640, extra_parameters: {} }
}

function clear() {
  name.value = ''
  description.value = ''
  config.value = defaultConfig()
  rawDirty.value = false
  editorKey.value += 1
  ElMessage.success('已清空，核心参数已恢复默认值。')
}

async function save() {
  if (!name.value.trim()) return
  saving.value = true
  try {
    const created = await createHyperparameterTemplate({
      name: name.value,
      description: description.value,
      ...config.value,
      derived_from_id: derivedFromId.value,
    })
    await router.push(`/hyperparameter-templates/${created.id}`)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '模板创建失败')
  } finally {
    saving.value = false
  }
}

async function saveCurrent() {
  if (!source.value || !name.value.trim()) return
  saving.value = true
  try {
    source.value = await updateHyperparameterTemplate(source.value.id, {
      version: source.value.version,
      name: name.value,
      description: description.value,
      ...config.value,
    })
    ElMessage.success(`已保存到当前模板 v${source.value.version}。`)
    await router.push(`/hyperparameter-templates/${source.value.id}`)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '模板保存失败')
  } finally {
    saving.value = false
  }
}

async function derive() {
  if (!source.value) return
  let nextName: string
  try {
    const result = await ElMessageBox.prompt('请输入派生模板名称', '派生模板', {
      inputValue: `${source.value.name} - 派生`,
      inputValidator: (value) => Boolean(value.trim()) || '请输入模板名称',
      confirmButtonText: '创建派生模板',
      cancelButtonText: '取消',
    })
    nextName = result.value.trim()
  } catch {
    return
  }
  saving.value = true
  try {
    const created = await createHyperparameterTemplate({
      name: nextName,
      description: description.value,
      ...config.value,
      derived_from_id: source.value.id,
    })
    ElMessage.success('已创建派生模板。')
    await router.push(`/hyperparameter-templates/${created.id}`)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '派生模板创建失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  const sourceId = editing.value
    ? String(route.params.id)
    : typeof route.query.from === 'string'
      ? route.query.from
      : null
  const [nextCatalog, loadedSource] = await Promise.all([
    getHyperparameterCatalog(),
    sourceId
      ? getHyperparameterTemplate(sourceId)
      : Promise.resolve(null),
  ])
  catalog.value = nextCatalog.items
  if (!loadedSource) return
  source.value = loadedSource
  derivedFromId.value = editing.value ? null : loadedSource.id
  name.value = editing.value ? loadedSource.name : `${loadedSource.name} - 派生`
  description.value = loadedSource.description
  config.value = {
    epochs: loadedSource.epochs,
    batch_mode: loadedSource.batch_mode,
    batch_value: loadedSource.batch_value,
    image_size: loadedSource.image_size,
    extra_parameters: structuredClone(loadedSource.extra_parameters),
  }
})
</script>

<template>
  <main class="content-page editor-page">
    <PageHeader
      :title="title"
      back-to="/hyperparameter-templates"
    >
      <template #meta>
        YOLO Detect / {{ catalog.length }} 个可选参数<span v-if="source"> · v{{ source.version }}</span>
      </template>
      <template #actions>
        <VButton v-if="!editing" variant="quiet" @click="clear">清空</VButton>
        <VButton v-if="editing" variant="default" :disabled="rawDirty" @click="derive">
          派生模板
        </VButton>
        <VButton
          variant="primary"
          :loading="saving"
          :disabled="!name.trim() || rawDirty"
          @click="editing ? saveCurrent() : save()"
        >
          {{ editing ? '保存当前模板' : '创建模板' }}
        </VButton>
      </template>
    </PageHeader>

    <div class="editor-body">
      <section class="identity-pane">
        <el-form label-position="top">
          <el-form-item label="模板名称">
            <el-input v-model="name" maxlength="128" show-word-limit />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="description" type="textarea" :rows="2" maxlength="2000" />
          </el-form-item>
        </el-form>
      </section>
      <HyperparameterConfigEditor
        :key="editorKey"
        v-model="config"
        :catalog="catalog"
        @dirty-change="rawDirty = $event"
      />
    </div>
  </main>
</template>

<style scoped>
.editor-page {
  background: var(--vdw-app);
  color: var(--vdw-ink);
}

.editor-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 24px;
}

.identity-pane {
  padding: 20px 24px 4px;
  border: 1px solid var(--vdw-line);
  border-radius: var(--vdw-radius-card);
  background: var(--vdw-surface);
  box-shadow: var(--vdw-shadow);
}

.identity-pane :deep(.el-form) {
  display: grid;
  grid-template-columns: minmax(300px, 0.8fr) minmax(480px, 1.2fr);
  gap: 20px;
}
</style>
