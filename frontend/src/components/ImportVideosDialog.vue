<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  importLocal,
  importRemote,
  previewLocal,
  previewRemote,
  type ImportBatch,
  type RemotePreview,
} from '../api/media'
import { VIDEO_EXTENSIONS } from '../api/filesystem'
import ServerFilePicker from './ServerFilePicker.vue'
import VButton from '../ui/VButton.vue'

const props = defineProps<{ modelValue: boolean; projectId: string }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submitted: [batch: ImportBatch]
}>()
const tab = ref<'local' | 'remote'>('local')
const selectedLocalFiles = ref<string[]>([])
const selectedLocalDirectory = ref('')
const remoteUrl = ref('')
const remoteItems = ref<RemotePreview[]>([])
const selected = ref<string[]>([])
const parsing = ref(false)
const submitting = ref(false)
const error = ref('')

function remoteTitle(item: RemotePreview) {
  return item.title.trim() || item.external_id.trim() || item.url
}

const candidates = computed(() => remoteItems.value.map((item) => ({
  key: item.url,
  title: remoteTitle(item),
  source: item.extractor.trim() || 'remote',
  detail: item.playlist
    ? `${item.playlist} · #${item.playlist_index ?? '-'} · ${item.url}`
    : item.url,
})))
const allRemoteSelected = computed(() => candidates.value.length > 0
  && candidates.value.every((item) => selected.value.includes(item.key)))
const someRemoteSelected = computed(() => candidates.value
  .some((item) => selected.value.includes(item.key)))
const canSubmit = computed(() => tab.value === 'local'
  ? Boolean(selectedLocalDirectory.value || selectedLocalFiles.value.length)
  : Boolean(selected.value.length))
const submitLabel = computed(() => {
  if (tab.value === 'remote') return `创建 ${selected.value.length} 个导入任务`
  return selectedLocalDirectory.value
    ? '导入选中目录下的视频'
    : `导入选中的 ${selectedLocalFiles.value.length} 个视频`
})

function toggleRemote(key: string) {
  selected.value = selected.value.includes(key)
    ? selected.value.filter((item) => item !== key)
    : [...selected.value, key]
}

function toggleAllRemote() {
  selected.value = allRemoteSelected.value
    ? []
    : candidates.value.map((item) => item.key)
}

async function parse() {
  parsing.value = true
  error.value = ''
  selected.value = []
  try {
    remoteItems.value = await previewRemote(props.projectId, remoteUrl.value)
    selected.value = remoteItems.value.map((item) => item.url)
    if (!selected.value.length) error.value = '没有找到可导入的视频'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '视频解析失败'
  } finally {
    parsing.value = false
  }
}

async function submit() {
  if (!canSubmit.value) return
  submitting.value = true
  error.value = ''
  try {
    let batch: ImportBatch
    if (tab.value === 'local') {
      let paths = selectedLocalFiles.value
      if (selectedLocalDirectory.value) {
        paths = (await previewLocal(props.projectId, selectedLocalDirectory.value))
          .map((item) => item.path)
        if (!paths.length) {
          error.value = '没有找到可导入的视频'
          return
        }
      }
      batch = await importLocal(props.projectId, paths)
    } else {
      batch = await importRemote(
        props.projectId,
        remoteItems.value
          .filter((item) => selected.value.includes(item.url))
          .map((item) => ({ title: remoteTitle(item), url: item.url })),
      )
    }
    emit('submitted', batch)
    emit('update:modelValue', false)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '导入任务创建失败'
  } finally {
    submitting.value = false
  }
}

watch(tab, () => {
  selectedLocalFiles.value = []
  selectedLocalDirectory.value = ''
  selected.value = []
  remoteItems.value = []
  error.value = ''
})
</script>

<template>
  <el-dialog
    append-to-body
    :model-value="modelValue"
    title="导入视频"
    top="3vh"
    width="min(1040px, calc(100vw - 32px))"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-tabs v-model="tab">
      <el-tab-pane label="本地文件" name="local">
        <p class="instruction">直接选择一个或多个视频，或选择一个目录导入其第一层视频。</p>
        <ServerFilePicker
          v-model="selectedLocalFiles"
          v-model:selected-directory="selectedLocalDirectory"
          mode="multiple-files-or-directory"
          :allowed-extensions="VIDEO_EXTENSIONS"
        />
      </el-tab-pane>
      <el-tab-pane label="远程 URL" name="remote">
        <p class="instruction">支持 HTTP/HTTPS 单视频或播放列表；解析不会立即下载。</p>
        <div class="remote-entry">
          <el-input
            v-model="remoteUrl"
            data-test="remote-url"
            placeholder="https://..."
            @keyup.enter="parse"
          />
          <VButton variant="primary" data-test="preview-remote"
            :loading="parsing"
            :disabled="!remoteUrl.trim()"
            @click="parse">
            解析 URL
          </VButton>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-alert v-if="error" :title="error" type="error" :closable="false" />

    <section v-if="tab === 'remote' && candidates.length" class="candidate-panel">
      <div class="candidate-status">
        已解析 {{ candidates.length }} 个视频，已选择 {{ selected.length }}/{{ candidates.length }}
      </div>
      <div class="candidate-table">
        <div class="candidate-row candidate-header">
          <div class="selection-cell">
            <el-checkbox
              :model-value="allRemoteSelected"
              :indeterminate="someRemoteSelected && !allRemoteSelected"
              data-test="select-all-remote"
              aria-label="选择全部远程视频"
              @click="toggleAllRemote"
            />
          </div>
          <div>来源</div>
          <div>视频标题 / 地址</div>
          <div class="action-cell">操作</div>
        </div>
        <div class="candidate-body">
          <div
            v-for="item in candidates"
            :key="item.key"
            class="candidate-row candidate"
            :class="{ selected: selected.includes(item.key) }"
            :data-test="`remote-candidate-${item.key}`"
          >
            <div class="selection-cell">
              <el-checkbox
                :model-value="selected.includes(item.key)"
                :aria-label="`选择远程视频 ${item.title}`"
                @click="toggleRemote(item.key)"
              />
            </div>
            <span class="candidate-source" :title="item.source">{{ item.source }}</span>
            <button
              type="button"
              class="candidate-name"
              :title="item.title"
              @click="toggleRemote(item.key)"
            >
              <strong>{{ item.title }}</strong>
              <small :title="item.detail">{{ item.detail }}</small>
            </button>
            <div class="action-cell">
              <VButton
                variant="primary"
                size="sm"
                :data-test="`toggle-remote-${item.key}`"
                @click="toggleRemote(item.key)"
              >
                {{ selected.includes(item.key) ? '已选择' : '选择' }}
              </VButton>
            </div>
          </div>
        </div>
      </div>
    </section>

    <template #footer>
      <VButton variant="default" @click="emit('update:modelValue', false)">取消</VButton>
      <VButton variant="primary" data-test="submit-import"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="submit">
        {{ submitLabel }}
      </VButton>
    </template>
  </el-dialog>
</template>

<style scoped>
.instruction {
  margin: 0 0 15px;
  color: var(--vdw-ink-2);
  font-size: 14px;
}

.remote-entry {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 11px;
}

.candidate-panel {
  margin-top: 20px;
  overflow: hidden;
  border: 1px solid var(--vdw-line);
  border-radius: 8px;
  background: #fff;
}

.candidate-status {
  min-height: 34px;
  padding: 8px 15px;
  color: var(--vdw-ink-2);
  font-size: 13px;
  background: #fff;
  border-bottom: 1px solid var(--vdw-surface-3);
}

.candidate-table {
  --columns: 42px 100px minmax(0, 1fr) 112px;
}

.candidate-row {
  display: grid;
  grid-template-columns: var(--columns);
  align-items: center;
  gap: 12px;
  min-height: 46px;
  padding: 0 15px;
  font-size: 14px;
  line-height: 1.4;
  border-bottom: 1px solid var(--vdw-surface-3);
}

.candidate-header {
  min-height: 40px;
  color: var(--vdw-ink-2);
  font-size: 13px;
  font-weight: 650;
  background: var(--vdw-surface-2);
}

.candidate-body {
  height: clamp(180px, 28vh, 300px);
  overflow: auto;
}

.candidate:hover,
.candidate.selected {
  background: var(--vdw-accent-soft);
}

.selection-cell {
  display: flex;
  justify-content: center;
}

.candidate-source {
  overflow: hidden;
  color: var(--vdw-accent);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.candidate-name {
  display: grid;
  min-width: 0;
  padding: 7px 0;
  color: var(--vdw-ink);
  text-align: left;
  background: transparent;
  border: 0;
  cursor: pointer;
}

.candidate-name strong,
.candidate-name small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.candidate-name small {
  color: var(--vdw-ink-2);
  font-size: 13px;
  font-weight: 400;
}

.action-cell {
  text-align: right;
}

@media (max-width: 620px) {
  .remote-entry {
    grid-template-columns: 1fr;
  }

  .candidate-table {
    --columns: 34px 62px minmax(0, 1fr) 72px;
  }

  .candidate-row {
    gap: 8px;
    padding: 0 10px;
  }
}
</style>
