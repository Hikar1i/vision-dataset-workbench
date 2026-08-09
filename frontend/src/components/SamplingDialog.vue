<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  configureSampling,
  type PlanBatch,
  type SamplingConfig,
  type Video,
} from '../api/media'
import VButton from '../ui/VButton.vue'

const props = defineProps<{ modelValue: boolean; projectId: string; videos: Video[] }>()
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
const forceSampled = ref(false)

const hasExisting = computed(() => props.videos.some((video) => video.sampling !== null))
const hasSampled = computed(() =>
  props.videos.some((video) => (video.sampling?.extracted_frames ?? 0) > 0),
)
const locked = computed(() => hasSampled.value && !forceSampled.value)
const videoIds = computed(() => props.videos.map((video) => video.id))
const overwriteLevel = computed<'none' | 'configured' | 'sampled'>(() => {
  if (hasSampled.value) return 'sampled'
  return hasExisting.value ? 'configured' : 'none'
})

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

function resetForm() {
  const plan = props.videos.length === 1 ? props.videos[0]?.sampling : null
  mode.value = plan?.mode ?? 'target_frames'
  minimum.value = plan?.parameters.minimum ?? 50
  maximum.value = plan?.parameters.maximum ?? 200
  interval.value = plan?.parameters.interval ?? 30
  seconds.value = plan?.parameters.seconds ?? 1
  frames.value = plan?.parameters.frames ?? 1
  outputFormat.value = plan?.output_format ?? 'jpg'
  quality.value = plan?.output_quality ?? 2
  forceSampled.value = false
  result.value = null
  error.value = ''
}

watch(() => props.modelValue, (open) => open && resetForm(), { immediate: true })

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    const batch = await configureSampling(props.projectId, videoIds.value, {
      mode: mode.value,
      parameters: parameters.value,
      output_format: outputFormat.value,
      output_quality: quality.value,
    }, overwriteLevel.value)
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
    append-to-body
    :model-value="modelValue"
    title="配置采样方案"
    width="min(620px, calc(100vw - 32px))"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <p class="scope">将同一方案应用到 {{ videos.length }} 个视频；保存不会立即覆盖已有帧。</p>
    <el-alert
      v-if="hasSampled"
      type="warning"
      :closable="false"
      title="目标视频已按现有方案完成抽帧。修改方案后需要再次执行抽帧才会生效，当前采样帧暂时保留。"
    />
    <el-alert
      v-else-if="hasExisting"
      type="warning"
      :closable="false"
      title="目标视频已配置采样方案，再次保存将覆盖当前方案。"
    />
    <label v-if="hasSampled" class="force-switch">
      <el-switch v-model="forceSampled" data-test="force-sampling-overwrite" />
      强制修改采样方案
    </label>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <fieldset class="form-grid" data-test="sampling-form" :disabled="locked" :data-locked="locked">
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
    </fieldset>
    <ul v-if="result?.rejected.length" class="rejected">
      <li v-for="item in result.rejected" :key="item.input">{{ item.input }}：{{ item.reason }}</li>
    </ul>
    <template #footer>
      <VButton variant="secondary" @click="emit('update:modelValue', false)">取消</VButton>
      <VButton variant="primary" data-test="save-sampling" :loading="submitting" :disabled="!videos.length || locked" @click="submit">
        {{ hasExisting ? '覆盖保存' : '保存方案' }}
      </VButton>
    </template>
  </el-dialog>
</template>

<style scoped>
.scope { margin-top: 0; color: var(--vdw-ink-2); }
.form-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; min-width: 0; margin: 14px 0 0; padding: 0; border: 0; }
.force-switch { display: flex; grid-column: 1 / -1; grid-template-columns: auto 1fr; align-items: center; margin-top: 14px; }
label { display: grid; gap: 7px; color: #4c5967; font-size: 14px; }
input, select { box-sizing: border-box; width: 100%; min-height: 40px; padding: 8px 10px; border: 1px solid var(--vdw-line-2); background: white; }
.rejected { color: #c2413b; font-size: 13px; }
@media (max-width: 560px) { .form-grid { grid-template-columns: 1fr; } }
</style>
