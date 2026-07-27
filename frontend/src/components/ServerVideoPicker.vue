<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  createFilesystemDirectory,
  listFilesystem,
  type FilesystemItem,
} from '../api/media'

const props = withDefaults(defineProps<{
  modelValue: string
  kind?: 'video' | 'model'
  allowDirectorySelection?: boolean
  allowCreate?: boolean
}>(), {
  kind: 'video',
  allowDirectorySelection: true,
  allowCreate: true,
})
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
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
  else emit('update:modelValue', item.path)
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
      <button
        v-for="item in items"
        :key="item.path"
        type="button"
        class="entry"
        :class="{ selected: modelValue === item.path }"
        :data-test="`entry-${item.path}`"
        @click="choose(item)"
      >
        <span class="entry-type">{{ item.type === 'directory' ? 'DIR' : kind === 'model' ? 'MODEL' : 'VIDEO' }}</span>
        <strong>{{ item.name }}</strong>
        <span>{{ item.type === 'directory' ? '打开' : '选择' }}</span>
      </button>
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
        <el-button v-if="allowDirectorySelection" data-test="select-directory" @click="emit('update:modelValue', current)">
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
  gap: 13px;
  width: 100%;
  padding: 12px 15px;
  color: #17212b;
  text-align: left;
  background: white;
  border: 0;
  border-bottom: 1px solid #edf0f4;
  cursor: pointer;
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

.entry > span:last-child {
  color: #687482;
  font-size: 13px;
}

@media (max-width: 620px) {
  header,
  footer {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
