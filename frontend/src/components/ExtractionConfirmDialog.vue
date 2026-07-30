<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

import type { Video } from '../api/media'

const props = defineProps<{ modelValue: boolean; videos: Video[] }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirmed: [level: 'light' | 'destructive']
}>()

const annotatedCount = computed(() => props.videos.filter((video) => video.has_annotations).length)
const screenedCount = computed(() =>
  props.videos.filter((video) => (video.sampling?.frame_revision ?? 0) > 1).length,
)
const sampledCount = computed(() =>
  props.videos.filter((video) => (video.sampling?.extracted_frames ?? 0) > 0).length,
)
const destructive = computed(() => annotatedCount.value > 0 || screenedCount.value > 0)
const countdown = ref(0)
let timer: ReturnType<typeof setInterval> | undefined

function clearTimer() {
  if (timer !== undefined) clearInterval(timer)
  timer = undefined
}

function startTimer() {
  clearTimer()
  countdown.value = destructive.value ? 3 : 0
  if (!countdown.value) return
  timer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) clearTimer()
  }, 1000)
}

function close() {
  clearTimer()
  emit('update:modelValue', false)
}

function confirm() {
  if (countdown.value > 0) return
  emit('confirmed', destructive.value ? 'destructive' : 'light')
  close()
}

watch(() => props.modelValue, (open) => open ? startTimer() : clearTimer(), { immediate: true })
onUnmounted(clearTimer)
</script>

<template>
  <el-dialog
    append-to-body
    :model-value="modelValue"
    :title="destructive ? '确认覆盖现有采样成果' : '确认重新抽帧'"
    width="min(560px, calc(100vw - 32px))"
    @update:model-value="!$event && close()"
  >
    <div class="overwrite-warning" :class="{ destructive }">
      <strong>将重新抽取 {{ videos.length }} 个视频的采样帧。</strong>
      <p>
        其中 {{ sampledCount }} 个视频的当前采样帧会被永久替换；所有新帧恢复为启用状态。
      </p>
      <template v-if="destructive">
        <p>以下已保存成果也会丢失，且无法撤销：</p>
        <ul>
          <li v-if="annotatedCount">{{ annotatedCount }} 个视频已有标注</li>
          <li v-if="screenedCount">{{ screenedCount }} 个视频保存过筛帧变更</li>
        </ul>
      </template>
      <p v-else>当前目标没有已保存标注或筛帧变更。</p>
    </div>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button
        data-test="confirm-overwrite"
        :type="destructive ? 'danger' : 'primary'"
        :disabled="countdown > 0"
        @click="confirm"
      >
        {{ countdown > 0 ? `确认覆盖（${countdown}）` : '确认覆盖并抽帧' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.overwrite-warning {
  color: #394854;
  line-height: 1.65;
}

.overwrite-warning.destructive {
  padding: 14px 16px;
  color: #8f2f35;
  background: #fff3f3;
  border: 1px solid #e8b4b7;
}

.overwrite-warning p {
  margin: 8px 0 0;
}

.overwrite-warning ul {
  margin: 6px 0 0;
  padding-left: 20px;
}
</style>
