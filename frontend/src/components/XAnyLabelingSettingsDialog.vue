<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { ref, watch } from 'vue'

import {
  saveXAnyLabelingSetting,
  type RemoteModelOption,
  type XAnyLabelingSetting,
} from '../api/models'
import VButton from '../ui/VButton.vue'

const props = defineProps<{
  modelValue: boolean
  setting: XAnyLabelingSetting | null
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [setting: XAnyLabelingSetting, models: RemoteModelOption[]]
}>()

const serverUrl = ref('')
const apiKey = ref('')
const clearApiKey = ref(false)
const saving = ref(false)

watch(
  () => [props.modelValue, props.setting] as const,
  ([open, setting]) => {
    if (!open) return
    serverUrl.value = setting?.server_url ?? ''
    apiKey.value = ''
    clearApiKey.value = false
  },
  { immediate: true },
)

async function save() {
  if (!serverUrl.value.trim()) return
  saving.value = true
  try {
    const mode = clearApiKey.value ? 'clear' : apiKey.value ? 'replace' : 'retain'
    const result = await saveXAnyLabelingSetting(
      serverUrl.value,
      mode,
      mode === 'replace' ? apiKey.value : null,
    )
    emit('saved', result.setting, result.models)
    emit('update:modelValue', false)
    ElMessage.success('X-anylabeling-server 设置已保存。')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '远程服务器设置保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    data-test="xanylabeling-settings-dialog"
    title="X-anylabeling-server 设置"
    width="min(560px, calc(100vw - 32px))"
    append-to-body
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="xanylabeling-settings-form">
      <label>
        <span>服务器地址</span>
        <el-input
          v-model="serverUrl"
          data-test="xanylabeling-server-url"
          placeholder="http://127.0.0.1:44444"
        />
      </label>
      <label>
        <span>API 密钥（可选）</span>
        <el-input
          v-model="apiKey"
          data-test="xanylabeling-api-key"
          type="password"
          show-password
          autocomplete="new-password"
          :placeholder="setting?.has_api_key ? '已配置，留空则保留' : '未配置'"
        />
      </label>
      <el-checkbox
        v-if="setting?.has_api_key"
        v-model="clearApiKey"
        data-test="xanylabeling-clear-api-key"
      >清除已保存的 API 密钥</el-checkbox>
    </div>
    <template #footer>
      <VButton
        variant="quiet"
        :disabled="saving"
        @click="emit('update:modelValue', false)"
      >取消</VButton>
      <VButton
        variant="primary"
        data-test="xanylabeling-settings-confirm"
        :loading="saving"
        :disabled="!serverUrl.trim()"
        :title="serverUrl.trim() ? '保存设置' : '请输入服务器地址'"
        @click="save"
      >确认</VButton>
    </template>
  </el-dialog>
</template>

<style scoped>
.xanylabeling-settings-form {
  display: grid;
  gap: 16px;
}

.xanylabeling-settings-form label {
  display: grid;
  gap: 7px;
  color: var(--vdw-ink-2);
  font-size: 14px;
}
</style>
