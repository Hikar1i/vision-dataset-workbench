<script setup lang="ts">
import { ref, watch } from 'vue'

import type {
  HyperparameterConfig,
  ParameterDefinition,
} from '../api/hyperparameters'
import type { TrainingResources } from '../api/training'
import VButton from '../ui/VButton.vue'
import HyperparameterConfigEditor from './HyperparameterConfigEditor.vue'

const props = defineProps<{
  modelValue: boolean
  config: HyperparameterConfig | null
  catalog: ParameterDefinition[]
  template: TrainingResources['templates'][number] | null
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  apply: [value: HyperparameterConfig]
  save: [value: HyperparameterConfig]
  derive: [value: HyperparameterConfig]
}>()

const draft = ref<HyperparameterConfig | null>(null)
const rawDirty = ref(false)

function cloneConfig(value: HyperparameterConfig): HyperparameterConfig {
  return { ...value, extra_parameters: { ...value.extra_parameters } }
}

watch(
  () => [props.modelValue, props.config] as const,
  ([open, value]) => {
    if (open && value) {
      draft.value = cloneConfig(value)
      rawDirty.value = false
    }
  },
  { immediate: true, deep: true },
)

function submit(action: 'apply' | 'save' | 'derive') {
  if (!draft.value || rawDirty.value) return
  const value = cloneConfig(draft.value)
  if (action === 'apply') emit('apply', value)
  else if (action === 'save') emit('save', value)
  else emit('derive', value)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    class="training-hyperparameter-dialog"
    width="min(1440px, calc(100vw - 48px))"
    destroy-on-close
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #header>
      <div class="dialog-title">
        <span>完整超参数编辑</span>
        <strong>{{ template?.name }} · v{{ template?.version }}</strong>
      </div>
    </template>
    <HyperparameterConfigEditor
      v-if="draft"
      v-model="draft"
      :catalog="catalog"
      @dirty-change="rawDirty = $event"
    />
    <template #footer>
      <div class="dialog-footer">
        <span>本次应用只更新当前训练草稿；保存草稿后才会持久化覆盖。</span>
        <div>
          <VButton variant="quiet" @click="emit('update:modelValue', false)">取消</VButton>
          <VButton variant="default" :disabled="rawDirty" @click="submit('apply')">
            本次应用
          </VButton>
          <VButton
            v-if="template?.can_edit"
            variant="default"
            :disabled="rawDirty"
            @click="submit('save')"
          >
            应用并保存
          </VButton>
          <VButton variant="primary" :disabled="rawDirty" @click="submit('derive')">
            应用并派生
          </VButton>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.dialog-title {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dialog-title span {
  color: var(--vdw-ink);
  font: 600 22px/1.2 var(--vdw-display);
}

.dialog-title strong,
.dialog-footer > span {
  color: var(--vdw-ink-2);
  font-size: 14px;
}

.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.dialog-footer > div {
  display: flex;
  gap: 8px;
}

:global(.training-hyperparameter-dialog) {
  display: flex;
  height: calc(100dvh - 48px);
  margin: 24px auto;
  flex-direction: column;
}

:global(.training-hyperparameter-dialog .el-dialog__body) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: var(--vdw-app);
}

:global(.training-hyperparameter-dialog .config-editor) {
  height: 100%;
  min-height: 0;
  grid-template-columns: minmax(500px, 1.15fr) minmax(340px, 0.85fr);
}

:global(.training-hyperparameter-dialog .form-pane),
:global(.training-hyperparameter-dialog .raw-pane) {
  min-height: 0;
}

:global(.training-hyperparameter-dialog .form-pane) {
  overflow-y: auto;
  scrollbar-gutter: stable;
}

:global(.training-hyperparameter-dialog .raw-pane) {
  overflow: hidden;
}

:global(.training-hyperparameter-dialog .config-editor .raw-pane textarea) {
  min-height: 0;
}

@media (prefers-reduced-motion: reduce) {
  :global(.training-hyperparameter-dialog *) {
    transition: none !important;
  }
}
</style>
