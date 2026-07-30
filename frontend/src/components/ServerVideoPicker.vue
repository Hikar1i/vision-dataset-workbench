<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  createFilesystemDirectory,
  listFilesystem,
  type FilesystemItem,
} from '../api/media'

const props = withDefaults(defineProps<{
  modelValue: string | string[]
  kind?: 'video' | 'model'
  allowDirectorySelection?: boolean
  allowCreate?: boolean
  multiple?: boolean
  selectedDirectory?: string
}>(), {
  kind: 'video',
  allowDirectorySelection: true,
  allowCreate: true,
  multiple: false,
  selectedDirectory: '',
})
const emit = defineEmits<{
  'update:modelValue': [value: string | string[]]
  'update:selectedDirectory': [value: string]
}>()
const current = ref('.')
const displayPath = ref('~')
const parent = ref<string | null>(null)
const items = ref<FilesystemItem[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const creating = ref(false)
const directoryName = ref('')
const error = ref('')

const breadcrumbs = computed(() => {
  const parts = current.value === '.' ? [] : current.value.split('/')
  return [
    { label: '~', path: '.' },
    ...parts.map((label, index) => ({
      label,
      path: parts.slice(0, index + 1).join('/'),
    })),
  ]
})

async function load(path: string, requestedPage = 1) {
  loading.value = true
  error.value = ''
  try {
    const result = await listFilesystem(path, requestedPage, props.kind)
    current.value = path
    displayPath.value = result.path
    parent.value = result.parent
    items.value = result.items
    page.value = result.page
    total.value = result.total
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '目录读取失败'
  } finally {
    loading.value = false
  }
}

function choose(item: FilesystemItem) {
  if (item.type === 'directory') void load(item.path)
  else if (props.multiple) toggleSelection(item)
  else emit('update:modelValue', item.path)
}

function isSelected(item: FilesystemItem) {
  return item.type === 'directory'
    ? props.selectedDirectory === item.path
    : Array.isArray(props.modelValue)
      ? props.modelValue.includes(item.path)
      : props.modelValue === item.path
}

function selectDirectory(path: string) {
  emit('update:modelValue', [])
  emit('update:selectedDirectory', props.selectedDirectory === path ? '' : path)
}

function toggleSelection(item: FilesystemItem) {
  if (item.type === 'directory') {
    selectDirectory(item.path)
    return
  }
  const selected = Array.isArray(props.modelValue) ? props.modelValue : []
  emit('update:selectedDirectory', '')
  emit(
    'update:modelValue',
    selected.includes(item.path)
      ? selected.filter((path) => path !== item.path)
      : [...selected, item.path],
  )
}

async function createDirectory() {
  if (!directoryName.value.trim()) return
  error.value = ''
  try {
    const created = await createFilesystemDirectory(current.value, directoryName.value)
    creating.value = false
    directoryName.value = ''
    emit('update:modelValue', created.path)
    await load(created.path)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '目录创建失败'
  }
}

onMounted(() => load('.'))
</script>

<template>
  <section class="server-picker">
    <header>
      <el-breadcrumb separator="/">
        <el-breadcrumb-item v-for="crumb in breadcrumbs" :key="crumb.path">
          <el-button link @click="load(crumb.path)">{{ crumb.label }}</el-button>
        </el-breadcrumb-item>
      </el-breadcrumb>
      <div>
        <el-button :disabled="parent === null" @click="parent !== null && load(parent)">
          上一级
        </el-button>
        <el-button @click="load(current)">刷新</el-button>
      </div>
    </header>

    <el-alert v-if="error" :title="error" type="error" :closable="false" />

    <div v-loading="loading" class="entry-list">
      <div
        v-for="item in items"
        :key="item.path"
        class="entry"
        :class="{ selected: isSelected(item), multiple }"
      >
        <el-checkbox
          v-if="multiple"
          :model-value="isSelected(item)"
          :aria-label="item.type === 'directory' ? `选择目录 ${item.name}` : `选择视频 ${item.name}`"
          :data-test="`select-${item.type === 'directory' ? 'directory' : 'file'}-${item.path}`"
          @click.stop="toggleSelection(item)"
        />
        <span class="entry-type">{{ item.type === 'directory' ? 'DIR' : kind === 'model' ? 'MODEL' : 'VIDEO' }}</span>
        <button type="button" class="entry-name" :data-test="`entry-${item.path}`" @click="choose(item)">
          {{ item.name }}
        </button>
        <button type="button" class="entry-action" @click="choose(item)">
          {{ item.type === 'directory' ? '打开' : isSelected(item) ? '已选择' : '选择' }}
        </button>
      </div>
    </div>

    <el-pagination
      v-if="total > 100"
      :current-page="page"
      :page-size="100"
      :total="total"
      layout="prev, pager, next"
      @current-change="(value: number) => load(current, value)"
    />

    <footer>
      <span>当前位置：{{ displayPath }}</span>
      <div>
        <el-button v-if="allowDirectorySelection" data-test="select-directory" @click="multiple ? selectDirectory(current) : emit('update:modelValue', current)">
          选择当前目录
        </el-button>
        <el-button v-if="allowCreate" data-test="new-directory" @click="creating = true">新建目录</el-button>
      </div>
    </footer>

    <el-dialog v-model="creating" append-to-body title="新建目录" width="462px">
      <el-input
        v-model="directoryName"
        data-test="directory-name"
        aria-label="目录名称"
        placeholder="目录名称"
      />
      <template #footer>
        <el-button
          data-test="create-directory"
          type="primary"
          :disabled="!directoryName.trim()"
          @click="createDirectory"
        >
          创建并选择
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.server-picker {
  border: 1px solid #d8dee6;
}

header,
footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 13px 15px;
  background: #f8fafc;
}

header {
  border-bottom: 1px solid #d8dee6;
}

footer {
  color: #687482;
  font-size: 13px;
  border-top: 1px solid #d8dee6;
}

.entry-list {
  min-height: 253px;
  max-height: 352px;
  overflow: auto;
}

.entry {
  display: grid;
  grid-template-columns: 62px minmax(0, 1fr) 44px;
  align-items: center;
  gap: 13px;
  width: 100%;
  min-height: 45px;
  padding: 0 15px;
  color: #17212b;
  text-align: left;
  background: white;
  border: 0;
  border-bottom: 1px solid #edf0f4;
  cursor: pointer;
}

.entry.multiple {
  grid-template-columns: 22px 62px minmax(0, 1fr) 52px;
}

.entry:hover,
.entry.selected {
  background: #eef7f5;
}

.entry-type {
  color: #16866f;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
}

.entry-name,
.entry-action {
  min-width: 0;
  padding: 12px 0;
  color: inherit;
  text-align: left;
  background: transparent;
  border: 0;
  cursor: pointer;
}

.entry-name {
  overflow: hidden;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entry-action {
  color: #687482;
  font-size: 13px;
  text-align: right;
}

@media (max-width: 620px) {
  header,
  footer {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
