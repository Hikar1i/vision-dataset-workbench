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
import ServerVideoPicker from './ServerVideoPicker.vue'

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

const candidates = computed(() => remoteItems.value.map((item) => ({
  key: item.url,
  title: item.title,
  detail: item.playlist
    ? `${item.playlist} · #${item.playlist_index ?? '-'}`
    : item.extractor,
})))
const canSubmit = computed(() => tab.value === 'local'
  ? Boolean(selectedLocalDirectory.value || selectedLocalFiles.value.length)
  : Boolean(selected.value.length))
const submitLabel = computed(() => {
  if (tab.value === 'remote') return `创建 ${selected.value.length} 个导入任务`
  return selectedLocalDirectory.value
    ? '导入选中目录下的视频'
    : `导入选中的 ${selectedLocalFiles.value.length} 个视频`
})

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
          .map((item) => ({ title: item.title, url: item.url })),
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
    width="min(860px, calc(100vw - 32px))"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-tabs v-model="tab">
      <el-tab-pane label="本地文件" name="local">
        <p class="instruction">直接选择一个或多个视频，或选择一个目录导入其第一层视频。</p>
        <ServerVideoPicker
          v-model="selectedLocalFiles"
          v-model:selected-directory="selectedLocalDirectory"
          multiple
          :allow-create="false"
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
          <el-button
            data-test="preview-remote"
            type="primary"
            :loading="parsing"
            :disabled="!remoteUrl.trim()"
            @click="parse"
          >
            解析 URL
          </el-button>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-alert v-if="error" :title="error" type="error" :closable="false" />

    <section v-if="tab === 'remote' && candidates.length" class="candidate-panel">
      <header><strong>选择要导入的视频</strong><span>{{ selected.length }}/{{ candidates.length }}</span></header>
      <el-checkbox-group v-model="selected">
        <div v-for="item in candidates" :key="item.key" class="candidate">
          <el-checkbox :value="item.key" />
          <span><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></span>
        </div>
      </el-checkbox-group>
    </section>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        data-test="submit-import"
        type="primary"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="submit"
      >
        {{ submitLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.instruction {
  margin: 0 0 15px;
  color: #687482;
  font-size: 14px;
}

.remote-entry {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 11px;
}

.candidate-panel {
  margin-top: 20px;
  border: 1px solid #d8dee6;
}

.candidate-panel > header,
.candidate {
  display: flex;
  align-items: center;
  gap: 13px;
}

.candidate-panel > header {
  justify-content: space-between;
  padding: 12px 15px;
  background: #f8fafc;
  border-bottom: 1px solid #d8dee6;
}

.candidate-panel > header span {
  color: #687482;
  font-size: 13px;
}

.el-checkbox-group {
  max-height: 286px;
  overflow: auto;
}

.candidate {
  padding: 11px 15px;
  border-bottom: 1px solid #edf0f4;
}

.candidate > span {
  display: grid;
  min-width: 0;
}

.candidate small {
  overflow: hidden;
  color: #687482;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 620px) {
  .remote-entry {
    grid-template-columns: 1fr;
  }
}
</style>
