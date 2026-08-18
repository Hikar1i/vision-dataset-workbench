<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Bottom, Top } from '@element-plus/icons-vue'

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
import { useProjectHeaderHost } from '../ui/projectHeaderHost'
import {
  randomLabelColor,
  readLabelColorCandidate,
  writeLabelColorCandidate,
} from './labelColor'
import VButton from '../ui/VButton.vue'

const props = defineProps<{ project: Project }>()
const labels = ref<ProjectLabel[]>([])
const names = reactive<Record<string, string>>({})
const descriptions = reactive<Record<string, string>>({})
const newName = ref('')
const newDescription = ref('')
const newColor = ref('')
const loading = ref(false)
const saving = ref('')
const error = ref('')
const canEdit = computed(() => props.project.role !== 'viewer')

function setLabels(value: ProjectLabel[]) {
  labels.value = value
  for (const key of Object.keys(names)) delete names[key]
  for (const key of Object.keys(descriptions)) delete descriptions[key]
  for (const label of value) {
    names[label.id] = label.name
    descriptions[label.id] = label.description_zh
  }
}

function replaceLabel(value: ProjectLabel) {
  const index = labels.value.findIndex((label) => label.id === value.id)
  if (index !== -1) labels.value[index] = value
  names[value.id] = value.name
  descriptions[value.id] = value.description_zh
}

function nextColor() {
  newColor.value = randomLabelColor(labels.value.map((label) => label.color))
  writeLabelColorCandidate(props.project.id, newColor.value)
}

function initializeColor() {
  const stored = readLabelColorCandidate(props.project.id)?.toLowerCase()
  if (/^#[0-9a-f]{6}$/.test(stored ?? '')) {
    newColor.value = stored ?? ''
    return
  }
  nextColor()
}

function saveSelectedColor() {
  writeLabelColorCandidate(props.project.id, newColor.value)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    setLabels(await listLabels(props.project.id))
    initializeColor()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '标签加载失败'
  } finally {
    loading.value = false
  }
}

async function add() {
  if (!newName.value.trim() || !newColor.value || saving.value) return
  saving.value = 'new'
  error.value = ''
  try {
    const label = await createLabel(
      props.project.id,
      newName.value,
      newDescription.value,
      newColor.value,
    )
    labels.value.push(label)
    names[label.id] = label.name
    descriptions[label.id] = label.description_zh
    newName.value = ''
    newDescription.value = ''
    nextColor()
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
    descriptions[label.id] = label.description_zh
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

function redescribe(label: ProjectLabel) {
  const description = descriptions[label.id]?.trim() ?? ''
  if (description === label.description_zh) {
    descriptions[label.id] = label.description_zh
    return
  }
  void change(label, { description_zh: description })
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

const headerHost = useProjectHeaderHost()
</script>

<template>
  <main class="content-page labels-shell">
    <Teleport defer :disabled="!headerHost" to="#project-page-meta">
      <span data-test="page-stat">{{ labels.length }} 个标签类别</span>
    </Teleport>

    <div class="content-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

      <section v-loading="loading" class="label-index">
        <form v-if="canEdit" class="label-create" @submit.prevent="add">
          <label class="create-field create-field--color">
            <span>颜色</span>
            <input
              v-model="newColor"
              class="color-input"
              data-test="new-label-color"
              type="color"
              aria-label="新标签颜色"
              @change="saveSelectedColor"
            />
          </label>
          <label class="create-field">
            <span>英文类别</span>
            <el-input
              v-model="newName"
              data-test="new-label-name"
              maxlength="64"
              placeholder="例如 helmet"
            />
          </label>
          <label class="create-field">
            <span>中文描述</span>
            <el-input
              v-model="newDescription"
              data-test="new-label-description"
              maxlength="64"
              placeholder="可选，例如 安全帽"
            />
          </label>
          <VButton variant="default" data-test="add-label" type="submit"
            :loading="saving === 'new'"
            :disabled="!newName.trim() || !newColor">添加</VButton>
        </form>

        <header
          v-if="labels.length"
          class="label-row label-header"
        >
          <span>映射顺序</span><span>启用状态</span><span>颜色</span><span>英文类别</span><span>中文描述</span><span>操作</span>
        </header>

        <article
          v-for="(label, index) in labels"
          :key="label.id"
          class="label-row"
        >
          <code class="mapping-order" :data-test="`order-${label.id}`">{{ label.sort_order }}</code>

          <el-switch
            :model-value="label.enabled"
            :data-test="`enabled-${label.id}`"
            inline-prompt
            :disabled="!canEdit || saving === label.id"
            @change="canEdit && change(label, { enabled: Boolean($event) })"
          />

          <div class="label-color" :data-test="`color-${label.id}`">
            <i :style="{ background: label.color }" />
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

          <el-input
            v-if="canEdit"
            v-model="descriptions[label.id]"
            :data-test="`description-${label.id}`"
            maxlength="64"
            :disabled="saving === label.id"
            @change="redescribe(label)"
          />
          <span v-else class="description-text">{{ label.description_zh || '—' }}</span>

          <div class="action-cell">
            <template v-if="canEdit">
              <VButton variant="quiet" size="sm" :data-test="`move-up-${label.id}`"
                aria-label="上移"
                :disabled="index === 0 || Boolean(saving)"
                @click="move(index, -1)"><el-icon><Top /></el-icon></VButton>
              <VButton variant="quiet" size="sm" :data-test="`move-down-${label.id}`"
                aria-label="下移"
                :disabled="index === labels.length - 1 || Boolean(saving)"
                @click="move(index, 1)"><el-icon><Bottom /></el-icon></VButton>
              <VButton variant="danger" size="sm" :loading="saving === label.id"
                @click="remove(label)">删除</VButton>
            </template>
          </div>
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
  background: var(--vdw-app);
}

.label-index {
  overflow-x: auto;
  background: white;
  border: 1px solid var(--vdw-line);
}

.label-create {
  display: flex;
  flex-wrap: wrap;
  gap: 11px;
  align-items: center;
  padding: 14px 18px;
  background: var(--vdw-surface-2);
  border-bottom: 1px solid var(--vdw-line);
}

.create-field {
  display: flex;
  flex: 0 1 350px;
  gap: 8px;
  align-items: center;
}

.create-field > span {
  flex: none;
  color: var(--vdw-ink-2);
  font-size: 13px;
}

.create-field--color {
  flex-basis: 74px;
}

.label-row {
  display: grid;
  grid-template-columns: 60px 110px 120px minmax(180px, 1fr) minmax(180px, 1fr) 210px;
  gap: 18px;
  align-items: center;
  min-width: 1040px;
  /* 与 VRow 保持一致 */
  min-height: var(--vdw-row-height);
  padding-top: 12px;
  padding-bottom: 12px;
  padding: 9px 18px;
  border-bottom: 1px solid var(--vdw-line);
}

.label-row:last-child {
  border-bottom: 0;
}

.label-header {
  min-height: 42px;
  padding-block: 0;
  color: var(--vdw-ink-2);
  font-size: 13px;
  background: var(--vdw-surface-2);
}

.action-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.color-input {
  width: 34px;
  height: 30px;
  padding: 2px;
  background: white;
  border: 1px solid var(--vdw-line);
  cursor: pointer;
}

.mapping-order {
  color: var(--vdw-ink-2);
  font: 16px var(--vdw-mono);
  justify-self: start;
}

.label-color {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.label-color i {
  flex: none;
  width: 18px;
  height: 18px;
  border: 1px solid rgb(23 33 43 / 18%);
  border-radius: 3px;
}

.label-color code {
  overflow: hidden;
  color: var(--vdw-ink-2);
  font: 13px var(--vdw-mono);
  text-overflow: ellipsis;
}

.description-text {
  color: var(--vdw-ink-2);
}

.label-empty {
  display: grid;
  gap: 7px;
  place-items: center;
  padding: 64px 20px;
  color: var(--vdw-ink-2);
}

.label-empty strong {
  color: var(--vdw-ink);
}

@media (max-width: 620px) {
  .label-create {
    align-items: stretch;
  }

  .create-field {
    flex-basis: 100%;
  }
}
</style>
