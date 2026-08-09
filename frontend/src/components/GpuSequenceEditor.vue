<script setup lang="ts">
import { computed } from "vue";
import type { GpuDevice, TrainingModelDraft } from "../api/training";
import VButton from '../ui/VButton.vue'
import VTag from '../ui/VTag.vue'

const props = defineProps<{
  models: TrainingModelDraft[];
  devices: GpuDevice[];
}>();
const emit = defineEmits<{ change: [TrainingModelDraft[]] }>();
const lanes = computed(() =>
  props.devices.map((device) => ({
    device,
    models: props.models
      .filter((model) => model.gpu_index === device.index)
      .sort((a, b) => a.queue_order - b.queue_order),
  })),
);
function move(model: TrainingModelDraft, delta: number) {
  const lane = props.models
    .filter((row) => row.gpu_index === model.gpu_index)
    .sort((a, b) => a.queue_order - b.queue_order);
  const index = lane.indexOf(model);
  const target = lane[index + delta];
  if (!target) return;
  const order = model.queue_order;
  model.queue_order = target.queue_order;
  target.queue_order = order;
  emit("change", [...props.models]);
}
function changeGpu(model: TrainingModelDraft, gpu: number) {
  model.gpu_index = gpu;
  model.queue_order =
    props.models.filter((row) => row !== model && row.gpu_index === gpu)
      .length + 1;
  emit("change", [...props.models]);
}
</script>

<template>
  <div class="gpu-lanes">
    <section v-for="lane in lanes" :key="lane.device.index" class="gpu-lane">
      <header>
        <strong>GPU {{ lane.device.index }}</strong
        ><span>{{ lane.device.name }}</span
        ><VTag
          :tone="
            lane.device.level === 'green'
              ? 'ok'
              : lane.device.level === 'orange'
                ? 'warn'
                : 'danger'
          "
          >显存 {{ lane.device.memory_percent }}%</VTag
        >
      </header>
      <article
        v-for="model in lane.models"
        :key="model.name + model.queue_order"
      >
        <code>q{{ String(model.queue_order).padStart(2, "0") }}</code
        ><span>{{ model.name }}</span>
        <el-select
          :model-value="model.gpu_index"
          aria-label="训练显卡"
          @update:model-value="changeGpu(model, Number($event))"
          ><el-option
            v-for="gpu in devices"
            :key="gpu.index"
            :label="`GPU ${gpu.index}`"
            :value="gpu.index"
        /></el-select>
        <VButton variant="secondary" title="上移"
          aria-label="上移"
          @click="move(model, -1)"/><VButton variant="secondary" title="下移"
          aria-label="下移"
          @click="move(model, 1)"/>
      </article>
      <el-empty
        v-if="!lane.models.length"
        description="此显卡暂无模型"
        :image-size="44"
      />
    </section>
  </div>
</template>

<style scoped>
.gpu-lanes {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
}
.gpu-lane {
  border: 1px solid var(--vdw-line);
  background: var(--vdw-surface-2);
}
.gpu-lane header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--vdw-line);
}
.gpu-lane header span {
  overflow: hidden;
  color: var(--vdw-ink-2);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gpu-lane article {
  display: grid;
  grid-template-columns: auto minmax(80px, 1fr) 92px auto auto;
  gap: 7px;
  align-items: center;
  padding: 9px 12px;
  border-bottom: 1px solid var(--vdw-line);
}
.gpu-lane code {
  color: var(--vdw-accent);
}
</style>
