<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { ApiError } from '../api/auth'
import {
  createLabel,
  deleteLabel,
  listLabels,
  reorderLabels,
  updateLabel,
  type LabelChanges,
  type ProjectLabel,
} from '../api/labels'
import type { Project } from '../api/projects'

const props = defineProps<{ project: Project }>()
const labels = ref<ProjectLabel[]>([])
const names = reactive<Record<string, string>>({})
const newName = ref('')
const newColor = ref('#16866f')
const loading = ref(false)
const saving = ref('')
const error = ref('')
const canEdit = computed(() => props.project.role !== 'viewer')

function setLabels(value: ProjectLabel[]) {
  labels.value = value
  for (const key of Object.keys(names)) delete names[key]
  for (const label of value) names[label.id] = label.name
}

function replaceLabel(value: ProjectLabel) {
  const index = labels.value.findIndex((label) => label.id === value.id)
  if (index !== -1) labels.value[index] = value
  names[value.id] = value.name
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    setLabels(await listLabels(props.project.id))
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '标签加载失败'
  } finally {
    loading.value = false
  }
}

async function add() {
  if (!newName.value.trim() || saving.value) return
  saving.value = 'new'
  error.value = ''
  try {
    const label = await createLabel(props.project.id, newName.value, newColor.value)
    labels.value.push(label)
    names[label.id] = label.name
    newName.value = ''
    ElMessage.success('标签已添加')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '标签添加失败'
  } finally {
    saving.value = ''
  }
}

async function change(label: ProjectLabel, changes: LabelChanges) {
  saving.value = label.id
  error.value = ''
  try {
    replaceLabel(await updateLabel(props.project.id, label, changes))
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '标签修改失败'
    names[label.id] = label.name
    if (reason instanceof ApiError && reason.status === 409) await load()
  } finally {
    saving.value = ''
  }
}

function rename(label: ProjectLabel) {
  const name = names[label.id]?.trim()
  if (!name || name === label.name) {
    names[label.id] = label.name
    return
  }
  void change(label, { name })
}

function recolor(label: ProjectLabel, event: Event) {
  const color = (event.target as HTMLInputElement).value
  if (color !== label.color) void change(label, { color })
}

async function move(index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= labels.value.length || saving.value) return
  const ordered = [...labels.value]
  const current = ordered[index]
  ordered[index] = ordered[target]
  ordered[target] = current
  saving.value = 'order'
  error.value = ''
  try {
    setLabels(await reorderLabels(props.project.id, ordered.map((label) => label.id)))
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '标签排序保存失败'
  } finally {
    saving.value = ''
  }
}

async function remove(label: ProjectLabel) {
  try {
    await ElMessageBox.confirm(
      `删除标签“${label.name}”？`,
      '删除标签',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  saving.value = label.id
  error.value = ''
  try {
    await deleteLabel(props.project.id, label.id)
    await load()
    ElMessage.success('标签已删除')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '标签删除失败'
  } finally {
    saving.value = ''
  }
}

onMounted(load)
</script>

<template>
  <main class="content-page labels-shell">
    <header class="content-toolbar">
      <div class="content-toolbar-title">
        <h1>标签管理</h1>
        <span>{{ labels.length }} 个类别</span>
      </div>
    </header>

    <div class="content-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

      <section v-loading="loading" class="label-index">
        <form v-if="canEdit" class="label-create" @submit.prevent="add">
          <input v-model="newColor" class="color-input" type="color" aria-label="新标签颜色" />
          <el-input
            v-model="newName"
            data-test="new-label-name"
            maxlength="64"
            placeholder="输入英文类别，例如 helmet"
          />
          <el-button
            data-test="add-label"
            native-type="submit"
            type="primary"
            :loading="saving === 'new'"
            :disabled="!newName.trim()"
          >添加标签</el-button>
        </form>

        <header
          v-if="labels.length"
          class="label-row label-header"
          :class="{ 'label-row--readonly': !canEdit }"
        >
          <span>颜色</span><span>英文类别</span><span>状态</span><span>顺序</span><span v-if="canEdit">操作</span>
        </header>

        <article
          v-for="(label, index) in labels"
          :key="label.id"
          class="label-row"
          :class="{ 'label-row--readonly': !canEdit }"
        >
          <div class="color-cell">
            <input
              v-if="canEdit"
              class="color-input"
              type="color"
              :value="label.color"
              :aria-label="`${label.name}颜色`"
              :disabled="saving === label.id"
              @change="recolor(label, $event)"
            />
            <span v-else class="color-swatch" :style="{ backgroundColor: label.color }" />
            <code>{{ label.color }}</code>
          </div>

          <el-input
            v-if="canEdit"
            v-model="names[label.id]"
            :data-test="`name-${label.id}`"
            maxlength="64"
            :disabled="saving === label.id"
            @change="rename(label)"
          />
          <strong v-else>{{ label.name }}</strong>

          <el-switch
            v-if="canEdit"
            :model-value="label.enabled"
            :data-test="`enabled-${label.id}`"
            inline-prompt
            active-text="启用"
            inactive-text="停用"
            :disabled="saving === label.id"
            @change="change(label, { enabled: Boolean($event) })"
          />
          <span v-else class="label-state" :data-enabled="label.enabled">
            {{ label.enabled ? '启用' : '停用' }}
          </span>

          <div class="order-cell">
            <code>{{ String(index + 1).padStart(2, '0') }}</code>
            <template v-if="canEdit">
              <el-button
                :data-test="`move-up-${label.id}`"
                text
                aria-label="上移"
                :disabled="index === 0 || Boolean(saving)"
                @click="move(index, -1)"
              >↑</el-button>
              <el-button
                :data-test="`move-down-${label.id}`"
                text
                aria-label="下移"
                :disabled="index === labels.length - 1 || Boolean(saving)"
                @click="move(index, 1)"
              >↓</el-button>
            </template>
          </div>

          <el-button
            v-if="canEdit"
            text
            type="danger"
            :loading="saving === label.id"
            @click="remove(label)"
          >删除</el-button>
        </article>

        <div v-if="!loading && !labels.length" class="label-empty">
          <strong>还没有标签</strong>
          <span>{{ canEdit ? '在上方添加第一个英文类别。' : '项目尚未配置标注类别。' }}</span>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.labels-shell {
  color: var(--vdw-ink);
  background: var(--vdw-canvas);
}

.label-index {
  overflow-x: auto;
  background: white;
  border: 1px solid var(--vdw-rule);
}

.label-create {
  display: grid;
  grid-template-columns: 44px minmax(240px, 480px) auto;
  gap: 11px;
  align-items: center;
  padding: 14px 18px;
  background: #f8fafc;
  border-bottom: 1px solid var(--vdw-rule);
}

.label-row {
  display: grid;
  grid-template-columns: 180px minmax(220px, 1fr) 110px 150px 72px;
  gap: 18px;
  align-items: center;
  min-width: 790px;
  min-height: 57px;
  padding: 9px 18px;
  border-bottom: 1px solid #e6eaf0;
}

.label-row:last-child {
  border-bottom: 0;
}

.label-header {
  min-height: 42px;
  padding-block: 0;
  color: var(--vdw-muted);
  font-size: 13px;
  background: #f8fafc;
}

.label-row--readonly {
  grid-template-columns: 180px minmax(220px, 1fr) 110px 150px;
}

.color-cell,
.order-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.color-input {
  width: 34px;
  height: 30px;
  padding: 2px;
  background: white;
  border: 1px solid var(--vdw-rule);
  cursor: pointer;
}

.color-swatch {
  width: 24px;
  height: 24px;
  border: 1px solid rgb(23 33 43 / 14%);
}

.color-cell code,
.order-cell code {
  color: var(--vdw-muted);
  font: 12px var(--vdw-mono);
}

.order-cell .el-button {
  margin: 0;
  padding-inline: 5px;
}

.label-state {
  width: fit-content;
  padding: 3px 8px;
  color: var(--vdw-muted);
  font-size: 12px;
  border: 1px solid var(--vdw-rule);
}

.label-state[data-enabled='true'] {
  color: #0f6c59;
  border-color: #78cdb6;
}

.label-empty {
  display: grid;
  gap: 7px;
  place-items: center;
  padding: 64px 20px;
  color: var(--vdw-muted);
}

.label-empty strong {
  color: var(--vdw-ink);
}

@media (max-width: 620px) {
  .label-create {
    grid-template-columns: 40px minmax(180px, 1fr);
  }

  .label-create .el-button {
    grid-column: 1 / -1;
  }
}
</style>
