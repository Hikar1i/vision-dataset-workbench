<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  createHyperparameterTemplate,
  getHyperparameterCatalog,
  getHyperparameterTemplate,
  type HyperparameterConfig,
  type ParameterDefinition,
} from '../api/hyperparameters'
import HyperparameterConfigEditor from '../components/HyperparameterConfigEditor.vue'
import PageHeader from '../components/PageHeader.vue'
import VButton from '../ui/VButton.vue'

const route = useRoute()
const router = useRouter()
const catalog = ref<ParameterDefinition[]>([])
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

onMounted(async () => {
  const [nextCatalog, source] = await Promise.all([
    getHyperparameterCatalog(),
    typeof route.query.from === 'string'
      ? getHyperparameterTemplate(route.query.from)
      : Promise.resolve(null),
  ])
  catalog.value = nextCatalog.items
  if (!source) return
  derivedFromId.value = source.id
  name.value = `${source.name} - 派生`
  description.value = source.description
  config.value = {
    epochs: source.epochs,
    batch_mode: source.batch_mode,
    batch_value: source.batch_value,
    image_size: source.image_size,
    extra_parameters: structuredClone(source.extra_parameters),
  }
})
</script>

<template>
  <main class="content-page editor-page">
    <PageHeader
      :title="derivedFromId ? '派生超参数模板' : '新建超参数模板'"
      back-to="/hyperparameter-templates"
    >
      <template #meta>YOLO Detect / {{ catalog.length }} 个可选参数</template>
      <template #actions>
        <VButton
          variant="primary"
          :loading="saving"
          :disabled="!name.trim() || rawDirty"
          @click="save"
        >
          创建模板
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
