<script setup lang="ts">
import { ref, watch } from 'vue'

import { frameImageUrl, listFrames, setFramesEnabled, type Frame, type SamplingSummary } from '../api/media'

const props = defineProps<{ modelValue: boolean; projectId: string; videoId: string; title: string; canEdit: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; updated: [] }>()
const frames = ref<Frame[]>([])
const sampling = ref<SamplingSummary | null>(null)
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const selected = ref<string[]>([])
const loading = ref(false)
const changing = ref(false)
const error = ref('')

async function load(nextPage = page.value) {
  if (!props.modelValue || !props.videoId) return
  loading.value = true
  error.value = ''
  try {
    const result = await listFrames(props.projectId, props.videoId, nextPage)
    frames.value = result.items
    sampling.value = result.sampling
    page.value = result.page
    pageSize.value = result.page_size
    total.value = result.total
    selected.value = []
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '采样帧加载失败'
  } finally { loading.value = false }
}

async function change(enabled: boolean, all = false) {
  if (!sampling.value) return
  changing.value = true
  error.value = ''
  try {
    sampling.value = await setFramesEnabled(props.projectId, props.videoId, enabled, all ? null : selected.value, sampling.value.frame_revision)
    await load()
    emit('updated')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '帧筛选保存失败'
  } finally { changing.value = false }
}

watch(() => props.modelValue, (open) => { if (open) void load(1) }, { immediate: true })
</script>

<template>
  <el-dialog :model-value="modelValue" :title="`采样帧 / ${title}`" width="min(1100px, calc(100vw - 24px))" :teleported="false" @update:model-value="emit('update:modelValue', $event)">
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <header class="toolbar">
      <span>{{ sampling?.enabled_frames ?? 0 }} / {{ sampling?.extracted_frames ?? total }} 帧启用</span>
      <div v-if="canEdit">
        <el-button data-test="disable-selected" :disabled="!selected.length" :loading="changing" @click="change(false)">停用所选</el-button>
        <el-button data-test="enable-selected" :disabled="!selected.length" :loading="changing" @click="change(true)">启用所选</el-button>
        <el-button data-test="restore-all" text type="primary" :loading="changing" @click="change(true, true)">恢复全部</el-button>
      </div>
    </header>
    <section v-loading="loading" class="frame-grid">
      <label v-for="frame in frames" :key="frame.id" class="frame-card" :data-enabled="frame.enabled">
        <img loading="lazy" :src="frameImageUrl(projectId, videoId, frame.id)" :alt="`第 ${frame.sequence} 帧`" />
        <span><input v-if="canEdit" v-model="selected" type="checkbox" :value="frame.id" />#{{ frame.sequence }} · {{ frame.time_offset.toFixed(2) }}s</span>
      </label>
    </section>
    <el-pagination v-if="total > pageSize" layout="prev, pager, next" :current-page="page" :page-size="pageSize" :total="total" @current-change="load" />
  </el-dialog>
</template>

<style scoped>
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; color: #687482; }
.frame-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 10px; min-height: 180px; }
.frame-card { overflow: hidden; border: 1px solid #d8dee6; background: #f8fafc; }
.frame-card[data-enabled='false'] { opacity: .48; }
.frame-card img { display: block; width: 100%; aspect-ratio: 16/9; object-fit: cover; background: #17212b; }
.frame-card span { display: flex; gap: 7px; padding: 8px; font: 11px ui-monospace, monospace; }
</style>
