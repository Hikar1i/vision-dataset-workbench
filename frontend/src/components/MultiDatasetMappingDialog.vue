<script setup lang="ts">
import { ArrowDown, ArrowUp, Delete, Refresh, Sort } from "@element-plus/icons-vue";
import { computed, ref, watch } from "vue";
import type { MultiDatasetConfig, TrainingResources } from "../api/training";
import VButton from "../ui/VButton.vue";
import {
  canonicalMapping,
  deleteTarget,
  mappingDraft,
  mappingValid,
  moveTarget,
  restoreTargets,
  syncMapping,
  targetSources,
  type MappingDraft,
} from "./multiDatasetMapping";

const props = defineProps<{
  modelValue: boolean;
  config: MultiDatasetConfig | null;
  datasets: TrainingResources["datasets"];
  title?: string;
}>();
const emit = defineEmits<{
  "update:modelValue": [boolean];
  save: [MultiDatasetConfig];
}>();
const search = ref("");
const working = ref<MappingDraft>({ selected: [], order: [], deleted: [] });
const expandedProjects = ref<string[]>([]);
const expandedSources = ref<string[]>([]);

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return;
    working.value = mappingDraft(props.config, props.datasets);
    search.value = "";
    expandedProjects.value = [...new Set(props.datasets.map((item) => item.project_id))];
    expandedSources.value = [];
  },
  { immediate: true },
);

const projects = computed(() => {
  const term = search.value.trim().toLocaleLowerCase();
  const groups = new Map<string, { id: string; name: string; datasets: typeof props.datasets }>();
  for (const dataset of props.datasets) {
    if (
      term &&
      !dataset.project_name.toLocaleLowerCase().includes(term) &&
      !dataset.name.toLocaleLowerCase().includes(term)
    ) continue;
    const group = groups.get(dataset.project_id) ?? {
      id: dataset.project_id,
      name: dataset.project_name,
      datasets: [],
    };
    group.datasets.push(dataset);
    groups.set(dataset.project_id, group);
  }
  return [...groups.values()];
});
const selectedDatasets = computed(() =>
  working.value.selected
    .map((id) => props.datasets.find((item) => item.id === id))
    .filter((item): item is TrainingResources["datasets"][number] => Boolean(item)),
);
const selectedImages = computed(() =>
  selectedDatasets.value.reduce((sum, item) => sum + item.total_frames, 0),
);
const valid = computed(() => mappingValid(working.value));

function selectDataset(id: string, selected: boolean) {
  if (selected && !working.value.selected.includes(id)) working.value.selected.push(id);
  if (!selected) working.value.selected = working.value.selected.filter((item) => item !== id);
  syncMapping(working.value, props.datasets);
}
function toggleProject(id: string) {
  expandedProjects.value = expandedProjects.value.includes(id)
    ? expandedProjects.value.filter((item) => item !== id)
    : [...expandedProjects.value, id];
}
function toggleSources(name: string) {
  expandedSources.value = expandedSources.value.includes(name)
    ? expandedSources.value.filter((item) => item !== name)
    : [...expandedSources.value, name];
}
function close() { emit("update:modelValue", false); }
function save() {
  if (!valid.value) return;
  emit("save", canonicalMapping(working.value));
  close();
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="title || '配置多数据集与类别重映射'"
    class="mapping-dialog"
    width="min(2100px, calc(100vw - 120px))"
    top="34px"
    append-to-body
    destroy-on-close
    @close="close"
  >
    <div class="mapping-layout">
      <aside class="dataset-pane">
        <label class="visible-label" for="mapping-search">选择数据集</label>
        <el-input id="mapping-search" v-model="search" clearable placeholder="搜索项目或数据集" />
        <div v-if="projects.length" class="dataset-tree">
          <section v-for="project in projects" :key="project.id" class="project-group">
            <button
              type="button"
              class="project-title"
              :aria-expanded="expandedProjects.includes(project.id)"
              @click="toggleProject(project.id)"
            >
              <strong>{{ project.name }}</strong><span>{{ project.datasets.length }} 个</span>
            </button>
            <div v-show="expandedProjects.includes(project.id)" class="project-datasets">
              <label v-for="dataset in project.datasets" :key="dataset.id" class="dataset-option">
                <el-checkbox
                  :model-value="working.selected.includes(dataset.id)"
                  :data-test="`dataset-${dataset.id}`"
                  @change="selectDataset(dataset.id, Boolean($event))"
                />
                <span class="dataset-copy"><b>{{ dataset.name }}</b><small>{{ dataset.total_frames.toLocaleString() }} 张图像 · {{ dataset.labels.length }} 个类别</small></span>
              </label>
            </div>
          </section>
        </div>
        <el-empty v-else description="没有匹配的可用数据集" :image-size="72" />
      </aside>

      <section class="mapping-pane">
        <header class="selection-summary">
          <div><b>已选数据集（{{ working.selected.length }}）</b><span>{{ selectedImages.toLocaleString() }} 张图像 · {{ working.order.length }} 个目标类别</span></div>
          <div class="selected-chips">
            <span v-for="dataset in selectedDatasets" :key="dataset.id" class="dataset-chip" :title="`${dataset.project_name} / ${dataset.name}`">
              <span>{{ dataset.project_name }} / {{ dataset.name }}</span>
              <button type="button" :aria-label="`移除 ${dataset.name}`" @click="selectDataset(dataset.id, false)">×</button>
            </span>
          </div>
          <el-alert title="不同来源可能包含重复图片；系统仅提示，不自动去重，也不会阻止训练。" type="warning" :closable="false" show-icon />
        </header>

        <div class="mapping-toolbar">
          <div><h3>目标类别映射</h3><p>目标名称只读；数组顺序就是最终 YOLO 类别索引。</p></div>
          <div>
            <VButton size="sm" :disabled="!working.deleted.length" @click="restoreTargets(working, datasets)">
              <template #icon><el-icon><Refresh /></el-icon></template>恢复已删除类别
            </VButton>
            <VButton size="sm" :disabled="!working.order.length">
              <template #icon><el-icon><Sort /></el-icon></template>索引已连续
            </VButton>
          </div>
        </div>

        <div class="mapping-table" role="table" aria-label="目标类别映射">
          <div class="mapping-row mapping-head" role="row">
            <span>目标索引</span><span>目标类别名</span><span>来源类别</span><span>操作</span>
          </div>
          <div v-for="(name, index) in working.order" :key="name" class="mapping-row" role="row">
            <code>{{ index }}</code>
            <b class="ellipsis" :title="name">{{ name }}</b>
            <div>
              <div class="source-list" :class="{ expanded: expandedSources.includes(name) }">
                <span v-for="source in targetSources(name, working.selected, datasets)" :key="`${source.dataset}-${source.index}`" class="source-chip" :title="`${source.project} / ${source.dataset} · ${source.index}:${source.name}`">
                  {{ source.dataset }} · {{ source.index }}:{{ source.name }}
                </span>
              </div>
              <button v-if="targetSources(name, working.selected, datasets).length > 3" type="button" class="expand-sources" :aria-expanded="expandedSources.includes(name)" @click="toggleSources(name)">
                {{ expandedSources.includes(name) ? "收起来源" : "展开全部来源" }}
              </button>
            </div>
            <div class="row-actions">
              <VButton variant="quiet" size="sm" icon-only label="上移" :disabled="index === 0" @click="moveTarget(working, index, -1)"><template #icon><el-icon><ArrowUp /></el-icon></template></VButton>
              <VButton variant="quiet" size="sm" icon-only label="下移" :disabled="index === working.order.length - 1" @click="moveTarget(working, index, 1)"><template #icon><el-icon><ArrowDown /></el-icon></template></VButton>
              <VButton variant="danger" size="sm" icon-only label="删除目标类别" @click="deleteTarget(working, name)"><template #icon><el-icon><Delete /></el-icon></template></VButton>
            </div>
          </div>
          <el-empty v-if="!working.order.length" description="请选择数据集并至少保留一个目标类别" :image-size="76" />
        </div>
      </section>
    </div>
    <template #footer>
      <div class="dialog-footer">
        <p :class="{ invalid: !valid }">{{ valid ? `映射有效：${working.order.length} 个连续目标类别` : "无法保存：至少选择一个数据集并保留一个目标类别" }}</p>
        <div><VButton @click="close">取消</VButton><VButton variant="primary" data-test="save-mapping" :disabled="!valid" @click="save">保存映射</VButton></div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.mapping-layout{display:grid;grid-template-columns:360px minmax(0,1fr);height:min(890px,calc(100vh - 190px));min-height:620px;border:1px solid var(--vdw-line);border-radius:var(--vdw-radius-card);overflow:hidden}.dataset-pane{padding:16px;overflow:auto;background:var(--vdw-surface-2);border-right:1px solid var(--vdw-line)}.visible-label{display:block;margin-bottom:7px;font-weight:500}.dataset-tree{display:grid;gap:8px;margin-top:14px}.project-group{border:1px solid var(--vdw-line);border-radius:var(--vdw-radius-control);background:var(--vdw-surface)}.project-title{display:flex;align-items:center;justify-content:space-between;width:100%;height:42px;padding:0 12px;border:0;background:transparent;cursor:pointer}.project-title:hover{background:var(--vdw-accent-soft)}.project-title span{color:var(--vdw-ink-3);font-size:14px}.project-datasets{display:grid;gap:2px;padding:0 8px 8px}.dataset-option{display:grid;grid-template-columns:auto minmax(0,1fr);gap:8px;align-items:start;padding:9px;border:1px solid transparent;border-radius:var(--vdw-radius-control);cursor:pointer}.dataset-option:hover{border-color:var(--vdw-line);background:var(--vdw-surface-2)}.dataset-copy{display:grid;min-width:0}.dataset-copy b,.dataset-copy small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dataset-copy small{color:var(--vdw-ink-2);font-size:14px}.mapping-pane{min-width:0;overflow:auto}.selection-summary{display:grid;gap:10px;padding:15px 18px;border-bottom:1px solid var(--vdw-line);background:var(--vdw-surface)}.selection-summary>div:first-child{display:flex;gap:14px;align-items:baseline}.selection-summary>div:first-child span{color:var(--vdw-ink-2);font-size:14px}.selected-chips{display:flex;flex-wrap:wrap;gap:6px;max-height:58px;overflow:auto}.dataset-chip{display:flex;align-items:center;gap:6px;max-width:300px;height:26px;padding:0 8px;border:1px solid var(--vdw-line-2);border-radius:999px;background:var(--vdw-surface-2);font-size:14px}.dataset-chip>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dataset-chip button{padding:0;border:0;background:transparent;color:var(--vdw-ink-2);font-size:16px}.mapping-toolbar{display:flex;align-items:center;justify-content:space-between;padding:14px 18px 10px}.mapping-toolbar h3{margin:0;font-size:17px}.mapping-toolbar p{margin:3px 0 0;color:var(--vdw-ink-2);font-size:14px}.mapping-toolbar>div:last-child,.dialog-footer>div{display:flex;gap:7px}.mapping-table{margin:0 18px 18px;border:1px solid var(--vdw-line);border-radius:var(--vdw-radius-card);overflow:hidden}.mapping-row{display:grid;grid-template-columns:100px minmax(160px,.8fr) minmax(280px,1.8fr) 126px;gap:16px;align-items:center;min-height:64px;padding:12px 14px;border-bottom:1px solid var(--vdw-line)}.mapping-row:last-child{border-bottom:0}.mapping-head{min-height:43px;background:var(--vdw-surface-3);color:var(--vdw-ink-2);font-size:14px;font-weight:500}.ellipsis{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.source-list{display:flex;flex-wrap:wrap;gap:5px;max-height:52px;overflow:hidden}.source-list.expanded{max-height:none}.source-chip{display:block;max-width:100%;padding:2px 7px;overflow:hidden;background:var(--vdw-surface-2);color:var(--vdw-ink-2);font:14px var(--vdw-mono);text-overflow:ellipsis;white-space:nowrap}.expand-sources{margin-top:4px;padding:0;border:0;background:transparent;color:var(--vdw-accent-ink);font-size:14px}.row-actions{display:flex;gap:4px}.dialog-footer{display:flex;align-items:center;justify-content:space-between}.dialog-footer p{margin:0;color:var(--vdw-ok);font-size:14px}.dialog-footer p.invalid{color:var(--vdw-danger)}
@media(prefers-reduced-motion:reduce){.project-datasets,.source-list{transition:none}}
</style>

<style>
.mapping-dialog{max-height:calc(100vh - 68px);margin-bottom:0}.mapping-dialog .el-dialog__body{padding:0 18px}.mapping-dialog .el-dialog__footer{padding:12px 18px 16px}
</style>
