<script setup lang="ts">
import { computed, ref } from 'vue'

import { configureSampling, type PlanBatch, type SamplingConfig } from '../api/media'

const props = defineProps<{ modelValue: boolean; projectId: string; videoIds: string[] }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submitted: [batch: PlanBatch]
}>()
const mode = ref<SamplingConfig['mode']>('target_frames')
const minimum = ref(50)
const maximum = ref(200)
const interval = ref(30)
const seconds = ref(1)
const frames = ref(1)
const outputFormat = ref<SamplingConfig['output_format']>('jpg')
const quality = ref(2)
const submitting = ref(false)
const error = ref('')
const result = ref<PlanBatch | null>(null)

const parameters = computed<Record<string, number>>(() => {
  const values: Record<string, number> = {}
  if (mode.value === 'target_frames') {
    values.minimum = minimum.value
    values.maximum = maximum.value
  } else if (mode.value === 'frame_interval') {
    values.interval = interval.value
  } else {
    values.seconds = seconds.value
    values.frames = frames.value
  }
  return values
})

function changeFormat() {
  quality.value = outputFormat.value === 'jpg' ? 2 : 6
}

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    const batch = await configureSampling(props.projectId, props.videoIds, {
      mode: mode.value,
      parameters: parameters.value,
      output_format: outputFormat.value,
      output_quality: quality.value,
    })
    result.value = batch
    emit('submitted', batch)
    if (!batch.rejected.length) emit('update:modelValue', false)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '采样方案保存失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="配置采样方案"
    width="min(620px, calc(100vw - 32px))"
    :teleported="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <p class="scope">将同一方案应用到 {{ videoIds.length }} 个视频；保存不会立即覆盖已有帧。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div class="form-grid">
      <label>采样模式
        <select v-model="mode" data-test="sampling-mode">
          <option value="target_frames">目标帧数</option>
          <option value="frame_interval">固定帧间隔</option>
          <option value="time_interval">时间间隔</option>
        </select>
      </label>
      <template v-if="mode === 'target_frames'">
        <label>短视频目标（10–100）<input v-model.number="minimum" type="number" min="10" max="100" /></label>
        <label>长视频上限（100–300）<input v-model.number="maximum" type="number" min="100" max="300" /></label>
      </template>
      <label v-else-if="mode === 'frame_interval'">每 N 帧采一帧
        <input v-model.number="interval" type="number" min="1" max="100000" />
      </label>
      <template v-else>
        <label>每 N 秒<input v-model.number="seconds" type="number" min="1" max="10" /></label>
        <label>采 M 帧<input v-model.number="frames" type="number" min="1" max="10" /></label>
      </template>
      <label>图片格式
        <select v-model="outputFormat" data-test="output-format" @change="changeFormat">
          <option value="jpg">JPG</option><option value="png">PNG</option>
        </select>
      </label>
      <label>{{ outputFormat === 'jpg' ? 'JPG 质量（1 最佳，31 最低）' : 'PNG 压缩（0–9）' }}
        <input v-model.number="quality" data-test="output-quality" type="number" :min="outputFormat === 'jpg' ? 1 : 0" :max="outputFormat === 'jpg' ? 31 : 9" />
      </label>
    </div>
    <ul v-if="result?.rejected.length" class="rejected">
      <li v-for="item in result.rejected" :key="item.input">{{ item.input }}：{{ item.reason }}</li>
    </ul>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button data-test="save-sampling" type="primary" :loading="submitting" :disabled="!videoIds.length" @click="submit">保存方案</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.scope { margin-top: 0; color: #687482; }
.form-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
label { display: grid; gap: 6px; color: #4c5967; font-size: 13px; }
input, select { box-sizing: border-box; width: 100%; min-height: 36px; padding: 7px 9px; border: 1px solid #cbd3dd; background: white; }
.rejected { color: #c2413b; font-size: 12px; }
@media (max-width: 560px) { .form-grid { grid-template-columns: 1fr; } }
</style>
