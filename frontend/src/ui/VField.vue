<script setup lang="ts">
/**
 * 表单字段外壳：可见标签 + 单位/范围提示 + 错误信息。
 * 输入框必须有可见标签；错误说明发生了什么，不使用模糊文案。
 */
import { useId } from 'vue'

const props = defineProps<{
  label: string
  /** 右侧灰色提示，例如单位或取值范围 */
  hint?: string
  /** 标签下方说明 */
  note?: string
  error?: string
  required?: boolean
}>()

const id = useId()
defineExpose({ id })
</script>

<template>
  <div class="vdw-field" :class="{ 'has-error': !!error }">
    <label :for="id">
      {{ label }}
      <abbr v-if="required" title="必填">*</abbr>
      <span v-if="hint" class="vdw-field__hint">{{ hint }}</span>
    </label>
    <slot :id="id" :invalid="!!props.error" />
    <p v-if="error" class="vdw-field__error" role="alert">{{ error }}</p>
    <p v-else-if="note" class="vdw-field__note">{{ note }}</p>
  </div>
</template>

<style scoped>
.vdw-field {
  min-width: 0;
}

.vdw-field label {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 6px;
  color: var(--vdw-ink-2);
  font-weight: 500;
  font-size: 14px;
}

.vdw-field abbr {
  color: var(--vdw-danger);
  text-decoration: none;
}

.vdw-field__hint {
  margin-left: auto;
  color: var(--vdw-ink-3);
  font: 400 13px/1 var(--vdw-mono);
}

.vdw-field__note,
.vdw-field__error {
  margin: 5px 0 0;
  font-size: 13px;
}

.vdw-field__note {
  color: var(--vdw-ink-3);
}

/* 错误不只靠颜色：同时有文字说明和输入框边框变化 */
.vdw-field__error {
  color: var(--vdw-danger);
}

.vdw-field.has-error :deep(.el-input__wrapper),
.vdw-field.has-error :deep(.vdw-input) {
  border-color: var(--vdw-danger);
  box-shadow: none;
}
</style>
