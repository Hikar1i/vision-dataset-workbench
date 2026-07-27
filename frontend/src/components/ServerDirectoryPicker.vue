<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { createSetupDirectory, listSetupDirectories, type DirectoryItem } from '../api/setup'

const props = defineProps<{ token: string; modelValue?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const current = ref('.')
const parent = ref<string | null>(null)
const displayPath = ref('~')
const items = ref<DirectoryItem[]>([])
const pageNumber = ref(1)
const total = ref(0)
const name = ref('')
const creating = ref(false)
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
  error.value = ''
  try {
    const page = await listSetupDirectories(props.token, path, requestedPage)
    current.value = path
    parent.value = page.parent
    displayPath.value = page.path
    items.value = page.items
    pageNumber.value = page.page
    total.value = page.total
    emit('update:modelValue', path)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取目录'
  }
}

async function createDirectory() {
  error.value = ''
  try {
    const result = await createSetupDirectory(props.token, current.value, name.value)
    creating.value = false
    name.value = ''
    await load(result.path)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法创建目录'
  }
}

function changePage(value: number) {
  void load(current.value, value)
}

onMounted(() => load(props.modelValue || '.'))
</script>

<template>
  <section class="directory-picker">
    <header>
      <el-breadcrumb separator="/">
        <el-breadcrumb-item v-for="crumb in breadcrumbs" :key="crumb.path">
          <el-button link @click="load(crumb.path)">{{ crumb.label }}</el-button>
        </el-breadcrumb-item>
      </el-breadcrumb>
      <span>
        <el-button :disabled="parent === null" @click="parent !== null && load(parent)">
          上一级
        </el-button>
        <el-button @click="load(current)">刷新</el-button>
      </span>
    </header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table :data="items" height="308">
      <el-table-column prop="name" label="目录">
        <template #default="scope">
          <el-button link :data-path="scope.row.path" @click="load(scope.row.path)">
            {{ scope.row.name }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-if="total > 100"
      :current-page="pageNumber"
      :page-size="100"
      :total="total"
      layout="prev, pager, next"
      @current-change="changePage"
    />
    <footer>
      <el-button data-test="new-directory" @click="creating = true">新建目录</el-button>
      <span>已选择：{{ displayPath }}</span>
    </footer>
    <el-dialog v-model="creating" append-to-body title="新建目录" width="462px">
      <el-input
        v-model="name"
        data-test="directory-name"
        aria-label="目录名称"
        placeholder="请输入目录名称"
      />
      <template #footer>
        <el-button data-test="create-directory" :disabled="!name" @click="createDirectory">
          创建并进入
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
header,
footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-block: 12px;
}
</style>
