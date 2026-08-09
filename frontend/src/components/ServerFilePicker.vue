<script setup lang="ts">
import { ArrowUp, Refresh, Search } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  createFilesystemDirectory,
  listFilesystem,
  type CreateFilesystemDirectory,
  type FilesystemEntry,
  type LoadFilesystemEntries,
} from '../api/filesystem'

export type ServerFilePickerMode = 'single-file' | 'multiple-files-or-directory' | 'directory'

const props = withDefaults(defineProps<{
  modelValue: string | string[]
  mode: ServerFilePickerMode
  allowedExtensions?: readonly string[]
  selectedDirectory?: string
  allowCreateDirectory?: boolean
  loadEntries?: LoadFilesystemEntries
  createDirectory?: CreateFilesystemDirectory
}>(), {
  allowedExtensions: () => [],
  selectedDirectory: '',
  allowCreateDirectory: false,
  loadEntries: undefined,
  createDirectory: undefined,
})
const emit = defineEmits<{
  'update:modelValue': [value: string | string[]]
  'update:selectedDirectory': [value: string]
}>()

const PAGE_SIZE = 100
const current = ref('.')
const displayPath = ref('~')
const parent = ref<string | null>(null)
const items = ref<FilesystemEntry[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const search = ref('')
const error = ref('')
const creating = ref(false)
const directoryName = ref('')
const createError = ref('')
let searchTimer: ReturnType<typeof setTimeout> | undefined
let requestId = 0

const loader = computed(() => props.loadEntries ?? listFilesystem)
const directoryCreator = computed(() => props.createDirectory ?? createFilesystemDirectory)
const multiple = computed(() => props.mode === 'multiple-files-or-directory')
const files = computed(() => items.value.filter((item) => item.type !== 'dir'))
const selectedFiles = computed(() => Array.isArray(props.modelValue) ? props.modelValue : [])
const allFilesSelected = computed(() =>
  files.value.length > 0 && files.value.every((item) => selectedFiles.value.includes(item.path)),
)
const someFilesSelected = computed(() =>
  files.value.some((item) => selectedFiles.value.includes(item.path)),
)
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

async function load(path: string, requestedPage = 1, requestedSearch = search.value.trim()) {
  const activeRequest = ++requestId
  loading.value = true
  error.value = ''
  try {
    const result = await loader.value({
      path,
      page: requestedPage,
      pageSize: PAGE_SIZE,
      extensions: props.mode === 'directory' ? [] : props.allowedExtensions,
      search: requestedSearch,
    })
    if (activeRequest !== requestId) return
    current.value = path
    displayPath.value = result.path
    parent.value = result.parent
    items.value = result.items
    page.value = result.page
    total.value = result.total
    if (props.mode === 'directory') emit('update:modelValue', path)
  } catch (reason) {
    if (activeRequest === requestId) {
      error.value = reason instanceof Error ? reason.message : '目录读取失败'
    }
  } finally {
    if (activeRequest === requestId) loading.value = false
  }
}

function isFileSelected(item: FilesystemEntry) {
  return Array.isArray(props.modelValue)
    ? props.modelValue.includes(item.path)
    : props.modelValue === item.path
}

function chooseFile(item: FilesystemEntry) {
  if (props.mode === 'single-file') {
    emit('update:modelValue', item.path)
    return
  }
  if (!multiple.value) return
  const next = isFileSelected(item)
    ? selectedFiles.value.filter((path) => path !== item.path)
    : [...selectedFiles.value, item.path]
  emit('update:selectedDirectory', '')
  emit('update:modelValue', next)
}

function selectDirectory(path: string) {
  if (!multiple.value) return
  emit('update:modelValue', [])
  emit('update:selectedDirectory', props.selectedDirectory === path ? '' : path)
}

function toggleVisibleFiles() {
  const visiblePaths = new Set(files.value.map((item) => item.path))
  const next = allFilesSelected.value
    ? selectedFiles.value.filter((path) => !visiblePaths.has(path))
    : [...new Set([...selectedFiles.value, ...visiblePaths])]
  emit('update:selectedDirectory', '')
  emit('update:modelValue', next)
}

async function createDirectoryEntry() {
  const name = directoryName.value.trim()
  if (!name) return
  createError.value = ''
  try {
    const created = await directoryCreator.value(current.value, name)
    creating.value = false
    directoryName.value = ''
    await load(created.path)
  } catch (reason) {
    createError.value = reason instanceof Error ? reason.message : '目录创建失败'
  }
}

watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => void load(current.value, 1), 250)
})

onMounted(() => load(
  props.mode === 'directory' && typeof props.modelValue === 'string'
    ? props.modelValue || '.'
    : '.',
))
onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
  requestId += 1
})
</script>

<template>
  <section class="server-file-picker">
    <header class="picker-toolbar">
      <el-breadcrumb separator="/" class="picker-breadcrumbs">
        <el-breadcrumb-item v-for="crumb in breadcrumbs" :key="crumb.path">
          <el-button link @click="load(crumb.path, 1)">{{ crumb.label }}</el-button>
        </el-breadcrumb-item>
      </el-breadcrumb>
      <div class="toolbar-actions">
        <el-input
          v-model="search"
          :prefix-icon="Search"
          clearable
          data-test="filesystem-search"
          aria-label="搜索当前目录"
          placeholder="搜索当前目录"
        />
        <el-button
          :icon="ArrowUp"
          :disabled="parent === null"
          title="返回上一级"
          aria-label="返回上一级"
          @click="parent !== null && load(parent, 1)"
        />
        <el-button
          :icon="Refresh"
          title="刷新当前目录"
          aria-label="刷新当前目录"
          @click="load(current, page)"
        />
      </div>
    </header>

    <div class="status-strip" :class="{ failed: error }">
      <span v-if="error">{{ error }}</span>
      <span v-else-if="search.trim()">当前目录找到 {{ total }} 项匹配内容</span>
      <span v-else>当前目录共 {{ total }} 项</span>
    </div>

    <div class="entry-table" :class="{ multiple }">
      <div class="entry-row entry-header">
        <div v-if="multiple" class="selection-cell">
          <el-checkbox
            :model-value="allFilesSelected"
            :indeterminate="someFilesSelected && !allFilesSelected"
            :disabled="files.length === 0"
            data-test="select-visible-files"
            aria-label="选择当前页全部文件"
            @click="toggleVisibleFiles"
          />
        </div>
        <div>类型</div>
        <div>文件名</div>
        <div class="action-cell">操作</div>
      </div>

      <div v-loading="loading" class="entry-body">
        <div
          v-for="item in items"
          :key="item.path"
          class="entry-row"
          :class="{
            selected: item.type === 'dir'
              ? selectedDirectory === item.path
              : isFileSelected(item),
          }"
          :data-test="`entry-${item.path}`"
        >
          <div v-if="multiple" class="selection-cell">
            <el-checkbox
              v-if="item.type !== 'dir'"
              :model-value="isFileSelected(item)"
              :data-test="`select-file-${item.path}`"
              :aria-label="`选择文件 ${item.name}`"
              @click="chooseFile(item)"
            />
          </div>
          <span class="entry-type" :data-test="`entry-type-${item.path}`">{{ item.type }}</span>
          <button
            type="button"
            class="entry-name"
            :title="item.name"
            @click="item.type === 'dir' ? load(item.path, 1) : chooseFile(item)"
          >
            {{ item.name }}
          </button>
          <div class="entry-actions action-cell">
            <template v-if="item.type === 'dir'">
              <el-button
                link
                :data-test="`open-directory-${item.path}`"
                @click="load(item.path, 1)"
              >
                打开
              </el-button>
              <el-button
                v-if="multiple"
                link
                type="primary"
                :data-test="`select-directory-${item.path}`"
                @click="selectDirectory(item.path)"
              >
                选择目录
              </el-button>
            </template>
            <el-button
              v-else-if="mode !== 'directory'"
              link
              type="primary"
              :data-test="`choose-file-${item.path}`"
              @click="chooseFile(item)"
            >
              {{ isFileSelected(item) ? '已选择' : '选择' }}
            </el-button>
          </div>
        </div>
        <el-empty v-if="!loading && items.length === 0" description="当前目录没有可选内容" />
      </div>
    </div>

    <el-pagination
      v-if="total > PAGE_SIZE"
      :current-page="page"
      :page-size="PAGE_SIZE"
      :total="total"
      layout="prev, pager, next"
      @current-change="(value: number) => load(current, value)"
    />

    <footer class="picker-footer">
      <span>当前位置：{{ displayPath }}</span>
      <div class="footer-actions">
        <el-button
          v-if="multiple"
          data-test="select-current-directory"
          @click="selectDirectory(current)"
        >
          选择当前目录
        </el-button>
        <el-button
          v-if="allowCreateDirectory"
          data-test="new-directory"
          @click="creating = true; createError = ''"
        >
          新建目录
        </el-button>
      </div>
    </footer>

    <el-dialog v-model="creating" append-to-body title="新建目录" width="462px">
      <el-input
        v-model="directoryName"
        data-test="directory-name"
        aria-label="目录名称"
        placeholder="请输入目录名称"
        @keyup.enter="createDirectoryEntry"
      />
      <p v-if="createError" class="create-error">{{ createError }}</p>
      <template #footer>
        <el-button @click="creating = false">取消</el-button>
        <el-button
          data-test="create-directory"
          type="primary"
          :disabled="!directoryName.trim()"
          @click="createDirectoryEntry"
        >
          创建并进入
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.server-file-picker {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  overflow: hidden;
  border: 1px solid #d8dee6;
  border-radius: 8px;
  background: #fff;
}

.picker-toolbar,
.picker-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 15px;
  background: #f8fafc;
}

.picker-toolbar {
  border-bottom: 1px solid #d8dee6;
}

.picker-breadcrumbs {
  min-width: 0;
}

.toolbar-actions,
.footer-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 8px;
}

.toolbar-actions .el-input {
  width: 240px;
}

.status-strip {
  min-height: 34px;
  padding: 8px 15px;
  color: #687482;
  font-size: 12px;
  background: #fff;
  border-bottom: 1px solid #edf0f4;
}

.status-strip.failed,
.create-error {
  color: #c0392b;
  background: #fff5f3;
}

.entry-table {
  --columns: 66px minmax(0, 1fr) 120px;
}

.entry-table.multiple {
  --columns: 42px 66px minmax(0, 1fr) 164px;
}

.entry-row {
  display: grid;
  grid-template-columns: var(--columns);
  align-items: center;
  gap: 12px;
  min-height: 46px;
  padding: 0 15px;
  border-bottom: 1px solid #edf0f4;
}

.entry-header {
  min-height: 40px;
  color: #536170;
  font-size: 12px;
  font-weight: 650;
  background: #f8fafc;
}

.entry-body {
  height: clamp(180px, 28vh, 300px);
  overflow: auto;
}

.entry-row:not(.entry-header):hover,
.entry-row.selected {
  background: #eef7f5;
}

.selection-cell {
  display: flex;
  justify-content: center;
}

.entry-type {
  color: #16866f;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
}

.entry-name {
  min-width: 0;
  overflow: hidden;
  padding: 13px 0;
  color: #17212b;
  font-weight: 650;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: transparent;
  border: 0;
  cursor: pointer;
}

.action-cell {
  text-align: right;
}

.entry-actions {
  white-space: nowrap;
}

.picker-footer {
  min-height: 54px;
  color: #687482;
  font-size: 13px;
  border-top: 1px solid #d8dee6;
}

.create-error {
  margin: 10px 0 0;
  padding: 8px 10px;
  border-radius: 4px;
}

@media (max-width: 720px) {
  .picker-toolbar,
  .picker-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .toolbar-actions .el-input {
    width: 100%;
  }

  .entry-table {
    --columns: 50px minmax(0, 1fr) 72px;
  }

  .entry-table.multiple {
    --columns: 34px 50px minmax(0, 1fr) 112px;
  }
}
</style>
