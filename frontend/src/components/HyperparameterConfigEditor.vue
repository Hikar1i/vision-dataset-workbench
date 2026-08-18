<script setup lang="ts">
import { Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { stringify } from 'yaml'
import { computed, reactive, ref, watch } from 'vue'

import {
  validateHyperparameterRaw,
  type BatchMode,
  type HyperparameterConfig,
  type ParameterDefinition,
  type ValidationIssue,
} from '../api/hyperparameters'
import VButton from '../ui/VButton.vue'
import CoreHyperparameterFields from './CoreHyperparameterFields.vue'

const props = defineProps<{
  modelValue: HyperparameterConfig
  catalog: ParameterDefinition[]
  compactCore?: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [value: HyperparameterConfig]
  'dirty-change': [value: boolean]
}>()

function cloneConfig(value: HyperparameterConfig): HyperparameterConfig {
  return { ...value, extra_parameters: { ...value.extra_parameters } }
}

const state = reactive<HyperparameterConfig>(cloneConfig(props.modelValue))
const selectedKey = ref('')
const raw = ref('')
const rawDirty = ref(false)
const issues = ref<ValidationIssue[]>([])
const parsing = ref(false)
const applying = ref(false)
const definitions = computed(() => Object.fromEntries(props.catalog.map((item) => [item.key, item])))
const available = computed(() => props.catalog.filter((item) => !(item.key in state.extra_parameters)))

function effectiveValues(value = state) {
  return {
    epochs: value.epochs,
    batch: value.batch_mode === 'auto' ? -1 : value.batch_value,
    imgsz: value.image_size,
    ...value.extra_parameters,
  }
}

function replace(value: HyperparameterConfig) {
  applying.value = true
  state.epochs = value.epochs
  state.batch_mode = value.batch_mode
  state.batch_value = value.batch_value
  state.image_size = value.image_size
  for (const key of Object.keys(state.extra_parameters)) delete state.extra_parameters[key]
  Object.assign(state.extra_parameters, value.extra_parameters)
  applying.value = false
}

function syncRaw() {
  if (!rawDirty.value) raw.value = stringify(effectiveValues(), { lineWidth: 0 })
}

function setRawDirty(value: boolean) {
  rawDirty.value = value
  emit('dirty-change', value)
}

function updateCore(key: 'epochs' | 'batch_mode' | 'batch_value' | 'image_size', value: unknown) {
  if (key === 'batch_mode') state.batch_mode = value as BatchMode
  else if (key === 'batch_value') state.batch_value = value as number | null
  else state[key] = Number(value)
}

function addParameter() {
  if (!selectedKey.value) return
  state.extra_parameters[selectedKey.value] = definitions.value[selectedKey.value].default
  selectedKey.value = ''
}

function removeParameter(key: string) {
  delete state.extra_parameters[key]
}

async function parse() {
  parsing.value = true
  try {
    const result = await validateHyperparameterRaw(raw.value)
    issues.value = result.issues
    if (!result.valid || !result.normalized) return
    replace(result.normalized)
    raw.value = result.normalized_raw ?? raw.value
    setRawDirty(false)
    ElMessage.success('RAW 已通过校验并解析到表单。')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : 'RAW 校验失败')
  } finally {
    parsing.value = false
  }
}

watch(
  () => props.modelValue,
  (value) => {
    if (JSON.stringify(value) !== JSON.stringify(state)) replace(value)
    syncRaw()
  },
  { deep: true, immediate: true },
)
watch(
  state,
  () => {
    if (applying.value) return
    emit('update:modelValue', cloneConfig(state))
    syncRaw()
  },
  { deep: true },
)

defineExpose({ hasUnparsedRaw: rawDirty })
</script>

<template>
  <div class="config-editor">
    <section class="form-pane">
      <CoreHyperparameterFields
        :epochs="state.epochs"
        :batch-mode="state.batch_mode"
        :batch-value="state.batch_value"
        :image-size="state.image_size"
        :compact="compactCore"
        @update:epochs="updateCore('epochs', $event)"
        @update:batch-mode="updateCore('batch_mode', $event)"
        @update:batch-value="updateCore('batch_value', $event)"
        @update:image-size="updateCore('image_size', $event)"
      />

      <div class="extra-heading">
        <div>
          <strong>附加超参数</strong>
          <p>从 Detect 参数目录中按需添加。</p>
        </div>
      </div>
      <div class="parameter-list">
        <div
          v-for="key in Object.keys(state.extra_parameters)"
          :key="key"
          class="parameter-row"
        >
          <label>
            <strong>{{ definitions[key]?.label }}</strong>
            <code>{{ key }}</code>
            <small v-if="definitions[key]?.minimum != null">
              {{ definitions[key]?.minimum }} – {{ definitions[key]?.maximum }}
            </small>
          </label>
          <el-switch
            v-if="definitions[key]?.value_type === 'boolean'"
            v-model="state.extra_parameters[key]"
          />
          <el-select v-else-if="key === 'cache'" v-model="state.extra_parameters[key]">
            <el-option label="关闭" :value="false" />
            <el-option label="内存 / ram" value="ram" />
            <el-option label="磁盘 / disk" value="disk" />
          </el-select>
          <el-select
            v-else-if="definitions[key]?.choices.length"
            v-model="state.extra_parameters[key]"
          >
            <el-option
              v-for="choice in definitions[key].choices"
              :key="choice"
              :label="choice"
              :value="choice"
            />
          </el-select>
          <el-input-number
            v-else
            v-model="state.extra_parameters[key] as number"
            :min="definitions[key]?.minimum ?? undefined"
            :max="definitions[key]?.maximum ?? undefined"
            :step="definitions[key]?.step"
            :precision="definitions[key]?.precision"
            :controls="definitions[key]?.controls"
          />
          <VButton
            variant="quiet"
            size="sm"
            icon-only
            :label="`移除 ${key}`"
            @click="removeParameter(String(key))"
          >
            <template #icon><el-icon><Close /></el-icon></template>
          </VButton>
        </div>
        <el-empty
          v-if="!Object.keys(state.extra_parameters).length"
          :image-size="72"
          description="尚未添加附加参数"
        />
        <div v-if="available.length" class="parameter-add">
          <el-select v-model="selectedKey" filterable placeholder="选择要添加的参数">
            <el-option
              v-for="item in available"
              :key="item.key"
              :label="`${item.label} / ${item.key}`"
              :value="item.key"
            />
          </el-select>
          <VButton variant="default" :disabled="!selectedKey" @click="addParameter">
            添加参数
          </VButton>
        </div>
      </div>
    </section>

    <aside class="raw-pane">
      <header>
        <div>
          <span>RAW / YAML</span>
          <strong>{{ rawDirty ? '有未解析更改' : '已与表单同步' }}</strong>
        </div>
        <VButton variant="default" :loading="parsing" @click="parse">校验并解析</VButton>
      </header>
      <textarea
        v-model="raw"
        spellcheck="false"
        aria-label="RAW 超参数 YAML"
        @input="setRawDirty(true); issues = []"
      />
      <el-alert
        v-if="rawDirty"
        title="RAW 更改尚未应用。只有全部校验通过后，左侧表单才会更新。"
        type="warning"
        :closable="false"
      />
      <ul v-if="issues.length" class="issues">
        <li v-for="(issue, index) in issues" :key="index">
          <code v-if="issue.line">L{{ issue.line }}{{ issue.key ? ` · ${issue.key}` : '' }}</code>
          {{ issue.message }}
        </li>
      </ul>
    </aside>
  </div>
</template>

<style scoped>
.config-editor {
  display: grid;
  grid-template-columns: minmax(520px, 1.2fr) minmax(360px, 0.8fr);
  gap: 18px;
}

.form-pane,
.raw-pane {
  min-width: 0;
  padding: 24px;
  border: 1px solid var(--vdw-line);
  border-radius: var(--vdw-radius-card);
  background: var(--vdw-surface);
  box-shadow: var(--vdw-shadow);
}

.extra-heading,
.raw-pane > header,
.raw-pane header > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.extra-heading p {
  margin: 4px 0;
  color: var(--vdw-ink-2);
}

.parameter-list {
  margin-top: 14px;
  border-top: 1px solid var(--vdw-line);
}

.parameter-row {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 220px 36px;
  gap: 14px;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--vdw-line);
}

.parameter-row label {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.parameter-row small {
  margin-top: 3px;
  color: var(--vdw-ink-3);
}

.parameter-row code,
.raw-pane header span {
  color: var(--vdw-accent);
  font: 13px var(--vdw-mono);
}

.parameter-add {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  padding-top: 16px;
}

.raw-pane {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.raw-pane header > div {
  align-items: flex-start;
  flex-direction: column;
}

.raw-pane textarea {
  flex: 1;
  min-height: 420px;
  resize: vertical;
  padding: 18px;
  border: 1px solid var(--vdw-focus-line);
  border-radius: var(--vdw-radius-control);
  background: var(--vdw-focus-canvas);
  color: var(--vdw-focus-ink);
  font: 14px/1.7 var(--vdw-mono);
  outline: none;
}

.raw-pane textarea:focus {
  box-shadow: var(--vdw-ring);
}

.issues {
  margin: 0;
  padding: 12px 16px 12px 32px;
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.issues code {
  margin-right: 8px;
}

@media (prefers-reduced-motion: reduce) {
  .config-editor * {
    transition: none !important;
  }
}
</style>
