<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string[]
  query: string
  labels: Array<{ id: string; name: string; enabled: boolean }>
  disabled?: boolean
  dataTest?: string
  placeholder?: string
  ariaLabel?: string
}>(), {
  disabled: false,
  dataTest: 'auto-categories',
  placeholder: '类别',
  ariaLabel: '自动标注类别',
})

const emit = defineEmits<{
  'update:modelValue': [values: string[]]
  'update:query': [query: string]
}>()

const normalizedQuery = computed(() => props.query.trim().toLowerCase())
const enabledLabels = computed(() => props.labels.filter((label) => label.enabled))
const visibleLabels = computed(() => enabledLabels.value.filter(
  (label) => !normalizedQuery.value || label.name.toLowerCase().includes(normalizedQuery.value),
))
const newCategory = computed(() => {
  const name = normalizedQuery.value
  if (!name || enabledLabels.value.some((label) => label.name.toLowerCase() === name)) return ''
  return name
})
const showAll = computed(() => (
  !normalizedQuery.value || 'all / 全类别'.includes(normalizedQuery.value)
))

function change(values: string[]) {
  const selectedAll = values.includes('__all__')
  const hadAll = props.modelValue.includes('__all__')
  emit(
    'update:modelValue',
    selectedAll && !hadAll ? ['__all__'] : values.filter((value) => value !== '__all__'),
  )
  emit('update:query', '')
}
</script>

<template>
  <el-select
    :model-value="modelValue"
    :data-test="dataTest"
    :aria-label="ariaLabel"
    multiple
    filterable
    collapse-tags
    :placeholder="placeholder"
    :disabled="disabled"
    :filter-method="(value: string) => emit('update:query', value)"
    @change="change"
  >
    <el-option
      v-if="newCategory"
      :label="`新建类别：${newCategory}`"
      :value="newCategory"
    />
    <el-option v-if="showAll" label="All / 全类别" value="__all__" />
    <el-option
      v-for="label in visibleLabels"
      :key="label.id"
      :label="label.name"
      :value="label.name"
    />
  </el-select>
</template>
