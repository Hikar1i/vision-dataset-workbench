<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from "vue";

import type { MultiDatasetConfig, TrainingResources } from "../api/training";
import VButton from "../ui/VButton.vue";

const props = withDefaults(defineProps<{
  mode: "single" | "multi";
  datasetId?: string | null;
  config?: MultiDatasetConfig | null;
  datasets: TrainingResources["datasets"];
  allowConfigure?: boolean;
}>(), {
  datasetId: null,
  config: null,
  allowConfigure: true,
});
const emit = defineEmits<{ configureMapping: [] }>();

const singleDataset = computed(() =>
  props.datasets.find((item) => item.id === props.datasetId),
);
const selectedDatasets = computed(() =>
  (props.config?.dataset_export_ids ?? [])
    .map((id) => props.datasets.find((item) => item.id === id))
    .filter((item): item is TrainingResources["datasets"][number] => Boolean(item)),
);
const classes = computed(() => props.mode === "single"
  ? [...(singleDataset.value?.labels ?? [])].sort((left, right) => left.index - right.index)
  : (props.config?.target_classes ?? []).map((name, index) => ({ index, name })),
);
const totalImages = computed(() => selectedDatasets.value.reduce(
  (sum, item) => sum + item.total_frames,
  0,
));

const componentId = useId().replace(/[^a-zA-Z0-9_-]/g, "");
const datasetListId = `dataset-summary-${componentId}-datasets`;
const classListId = `dataset-summary-${componentId}-classes`;
const datasetList = ref<HTMLElement>();
const classList = ref<HTMLElement>();
const datasetExpanded = ref(false);
const classExpanded = ref(false);
const datasetOverflow = ref(false);
const classOverflow = ref(false);
let observer: ResizeObserver | undefined;

function measureOverflow() {
  if (!datasetExpanded.value) {
    datasetOverflow.value = Boolean(
      datasetList.value && datasetList.value.scrollHeight > datasetList.value.clientHeight + 1,
    );
  }
  if (!classExpanded.value) {
    classOverflow.value = Boolean(
      classList.value && classList.value.scrollHeight > classList.value.clientHeight + 1,
    );
  }
}
function observeLists() {
  observer?.disconnect();
  if (datasetList.value) observer?.observe(datasetList.value);
  if (classList.value) observer?.observe(classList.value);
  measureOverflow();
}
function toggleDatasets() {
  datasetExpanded.value = !datasetExpanded.value;
  if (!datasetExpanded.value) void nextTick(measureOverflow);
}
function toggleClasses() {
  classExpanded.value = !classExpanded.value;
  if (!classExpanded.value) void nextTick(measureOverflow);
}

onMounted(() => {
  if (typeof ResizeObserver !== "undefined") observer = new ResizeObserver(measureOverflow);
  observeLists();
});
watch([datasetList, classList], () => void nextTick(observeLists), { flush: "post" });
watch(
  () => [props.mode, props.datasetId, props.config, props.datasets],
  () => {
    datasetExpanded.value = false;
    classExpanded.value = false;
    void nextTick(observeLists);
  },
  { deep: true },
);
onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <div v-if="mode === 'single' && singleDataset" class="dataset-selection-summary single-summary">
    <strong>{{ singleDataset.total_frames.toLocaleString() }} 张图像 · {{ classes.length }} 个类别</strong>
    <div class="chip-row">
      <div
        :id="classListId"
        ref="classList"
        class="chip-list"
        :class="{ expanded: classExpanded }"
        data-test="class-chip-list"
      >
        <span
          v-for="item in classes"
          :key="`${item.index}-${item.name}`"
          class="summary-chip class-chip"
          :title="`${item.index} : ${item.name}`"
        >{{ item.index }} : {{ item.name }}</span>
      </div>
      <button
        v-if="classOverflow"
        type="button"
        class="expand-trigger"
        :aria-label="classExpanded ? '收起全部类别' : '展开全部类别'"
        :aria-expanded="classExpanded"
        :aria-controls="classListId"
        :title="classExpanded ? '收起全部类别' : '展开全部类别'"
        @click="toggleClasses"
      >…</button>
    </div>
  </div>

  <section
    v-else-if="mode === 'multi'"
    class="dataset-selection-summary multi-summary-card"
    :class="{ invalid: !config }"
  >
    <header>
      <strong>{{ selectedDatasets.length }} 个数据集 · {{ totalImages.toLocaleString() }} 张图像</strong>
      <VButton
        v-if="allowConfigure"
        size="sm"
        variant="quiet"
        data-test="configure-mapping"
        @click="emit('configureMapping')"
      >{{ config ? "配置映射" : "开始配置" }}</VButton>
    </header>
    <div class="chip-row">
      <div
        :id="datasetListId"
        ref="datasetList"
        class="chip-list"
        :class="{ expanded: datasetExpanded }"
        data-test="dataset-chip-list"
      >
        <span
          v-for="item in selectedDatasets"
          :key="item.id"
          class="summary-chip dataset-chip"
          :title="`${item.project_name} / ${item.name}`"
        >{{ item.project_name }} / {{ item.name }}</span>
      </div>
      <button
        v-if="datasetOverflow"
        type="button"
        class="expand-trigger"
        :aria-label="datasetExpanded ? '收起全部数据集' : '展开全部数据集'"
        :aria-expanded="datasetExpanded"
        :aria-controls="datasetListId"
        :title="datasetExpanded ? '收起全部数据集' : '展开全部数据集'"
        @click="toggleDatasets"
      >…</button>
    </div>
    <strong>{{ classes.length }} 个目标类别</strong>
    <div class="chip-row">
      <div
        :id="classListId"
        ref="classList"
        class="chip-list"
        :class="{ expanded: classExpanded }"
        data-test="class-chip-list"
      >
        <span
          v-for="item in classes"
          :key="`${item.index}-${item.name}`"
          class="summary-chip class-chip"
          :title="`${item.index} : ${item.name}`"
        >{{ item.index }} : {{ item.name }}</span>
      </div>
      <button
        v-if="classOverflow"
        type="button"
        class="expand-trigger"
        :aria-label="classExpanded ? '收起全部类别' : '展开全部类别'"
        :aria-expanded="classExpanded"
        :aria-controls="classListId"
        :title="classExpanded ? '收起全部类别' : '展开全部类别'"
        @click="toggleClasses"
      >…</button>
    </div>
  </section>
</template>

<style scoped>
.dataset-selection-summary { display: grid; min-width: 0; gap: 8px; }
.single-summary { padding: 10px 12px; border: 1px solid var(--vdw-line); border-radius: var(--vdw-radius-control); background: var(--vdw-surface-2); }
.multi-summary-card { padding: 12px; border: 1px solid var(--vdw-accent-line); border-radius: var(--vdw-radius-control); background: var(--vdw-accent-soft); }
.multi-summary-card.invalid { border-color: var(--vdw-warn-line); background: var(--vdw-warn-soft); }
.multi-summary-card>header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.dataset-selection-summary strong { min-width: 0; font-size: 14px; }
.chip-row { display: flex; min-width: 0; align-items: flex-end; gap: 6px; }
.chip-list { display: flex; min-width: 0; flex: 1; flex-wrap: wrap; gap: 6px; max-height: 62px; overflow: hidden; transition: max-height 260ms var(--vdw-ease), opacity 260ms var(--vdw-ease); }
.chip-list.expanded { max-height: 360px; overflow: auto; }
.summary-chip { max-width: min(100%, 360px); height: 28px; padding: 3px 9px; overflow: hidden; border: 1px solid var(--vdw-line-2); border-radius: var(--vdw-radius-control); background: var(--vdw-surface-2); color: var(--vdw-ink-2); font-size: 14px; line-height: 20px; text-overflow: ellipsis; white-space: nowrap; }
.expand-trigger { flex: 0 0 34px; height: 28px; padding: 0; border: 1px solid var(--vdw-line); border-radius: var(--vdw-radius-control); background: var(--vdw-surface); color: var(--vdw-ink-2); font: 600 14px/1 var(--vdw-sans); cursor: pointer; transition: color var(--vdw-motion-fast) var(--vdw-ease), background-color var(--vdw-motion-fast) var(--vdw-ease), border-color var(--vdw-motion-fast) var(--vdw-ease), box-shadow var(--vdw-motion-fast) var(--vdw-ease); }
.expand-trigger:hover { color: var(--vdw-accent-ink); border-color: var(--vdw-accent-line); background: var(--vdw-accent-soft); box-shadow: inset 0 0 0 1px var(--vdw-accent-line); }
.expand-trigger:active { background: #cfe6ec; border-color: var(--vdw-accent); box-shadow: inset 0 1px 2px rgb(17 45 48 / 18%); }
@media (prefers-reduced-motion: reduce) { .chip-list, .expand-trigger { transition: none; } }
</style>
