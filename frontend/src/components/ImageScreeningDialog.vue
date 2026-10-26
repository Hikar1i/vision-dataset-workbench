<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { listImages, imageThumbnailUrl, setImagesEnabled, type ImageAsset, type ImageDirectory, type ImageFilters } from '../api/images'
import FrameAnnotationThumbnail from './FrameAnnotationThumbnail.vue'
import ImagePreviewDialog from './ImagePreviewDialog.vue'
import { applyEnabledPattern, diffEnabledStates, selectFrameRange, type EnabledState } from './frameFilter'
import VButton from '../ui/VButton.vue'
import { notify } from '../ui/notify'

const props = defineProps<{
  modelValue: boolean; projectId: string; projectName: string; filters: ImageFilters
  directories: ImageDirectory[]; canEdit: boolean; locked: boolean; labelColors: Record<string, string>
}>()
const emit = defineEmits<{'update:modelValue': [boolean]; updated: []}>()
const images = ref<ImageAsset[]>([])
const baseline = ref<EnabledState>({}), draft = ref<EnabledState>({})
const selected = ref(new Set<string>()), anchor = ref<string | null>(null), rangeMode = ref(false)
const loading = ref(false), saving = ref(false), error = ref(''), loadedCount = ref(0), expectedCount = ref(0)
const page = ref(1), pageSize = ref<50 | 100 | 200>(100), showAnnotations = ref(true), tileSize = ref(200)
const previewOpen = ref(false), previewId = ref<string | null>(null)
const patternOpen = ref(false), patternLength = ref(2), pattern = ref([true, false])
let generation = 0
const ids = computed(() => images.value.map(image => image.id))
const changes = computed(() => diffEnabledStates(ids.value, baseline.value, draft.value))
const editable = computed(() => props.canEdit && !props.locked && !loading.value && !saving.value)
const visible = computed(() => images.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const enabledCount = computed(() => images.value.filter(image => draft.value[image.id]).length)
const positiveCount = computed(() => images.value.filter(image => image.annotations.length).length)
const previewImage = computed(() => {
  const image = images.value.find(image => image.id === previewId.value)
  return image ? {...image, enabled: draft.value[image.id] ?? image.enabled} : null
})
watch(pageSize, () => {page.value = 1})
watch(patternLength, length => {
  pattern.value = Array.from({length}, (_, index) => pattern.value[index] ?? true)
})
watch(() => props.modelValue, open => {
  if (open) void load()
  else {generation++; previewOpen.value = false; patternOpen.value = false}
}, {immediate:true})

async function load() {
  const current = ++generation
  loading.value = true; error.value = ''; images.value = []; baseline.value = {}; draft.value = {}
  selected.value = new Set(); anchor.value = null; rangeMode.value = false; page.value = 1
  loadedCount.value = 0; expectedCount.value = 0
  const filters = {...props.filters}
  try {
    const first = await listImages(props.projectId, filters, 1, 200)
    if (current !== generation) return
    expectedCount.value = first.total
    const all = [...first.items]
    loadedCount.value = all.length
    for (let next = 2; next <= Math.ceil(first.total / first.page_size); next++) {
      const result = await listImages(props.projectId, filters, next, 200)
      if (current !== generation) return
      if (result.total !== first.total) throw new Error('图片范围已变化，请重新加载。')
      all.push(...result.items); loadedCount.value = all.length
    }
    if (all.length !== first.total || new Set(all.map(image => image.id)).size !== all.length) throw new Error('图片范围已变化，请重新加载。')
    images.value = all
    baseline.value = Object.fromEntries(all.map(image => [image.id, image.enabled]))
    draft.value = {...baseline.value}
  } catch (reason) {if (current === generation) error.value = reason instanceof Error ? reason.message : '图片加载失败'}
  finally {if (current === generation) loading.value = false}
}
function toggle(image: ImageAsset) {
  if (editable.value) draft.value = {...draft.value, [image.id]: !draft.value[image.id]}
}
function openImage(image: ImageAsset, shift: boolean) {
  if (!rangeMode.value) {previewId.value = image.id; previewOpen.value = true; return}
  if (shift && anchor.value) selected.value = selectFrameRange(ids.value, selected.value, anchor.value, image.id)
  else {
    const next = new Set(selected.value)
    if (next.has(image.id)) next.delete(image.id); else next.add(image.id)
    selected.value = next
  }
  anchor.value = image.id
}
function setSelected(value: boolean) {
  if (!editable.value) return
  draft.value = {...draft.value, ...Object.fromEntries([...selected.value].map(id => [id, value]))}
}
async function byAnnotations() {
  if (!editable.value) return
  const targets = rangeMode.value ? images.value.filter(image => selected.value.has(image.id)) : images.value
  if (!targets.length) return
  try {
    await ElMessageBox.confirm(`将对${rangeMode.value ? '选中的' : '当前范围全部'} ${targets.length} 张图片生成启停草稿：有目标框的启用，无目标框的停用。保存更改后才写入项目。`, '按标注启停', {type:'warning', confirmButtonText:'生成草稿', cancelButtonText:'取消'})
  } catch {return}
  if (!editable.value) return
  draft.value = {...draft.value, ...Object.fromEntries(targets.map(image => [image.id, image.annotations.length > 0]))}
}
function applyPattern() {
  if (!editable.value) return
  draft.value = applyEnabledPattern(ids.value, draft.value, pattern.value, rangeMode.value ? selected.value : undefined)
  patternOpen.value = false
}
async function save() {
  if (!editable.value || !changes.value.length) return
  saving.value = true; error.value = ''
  const byId = new Map(images.value.map(image => [image.id, image]))
  try {
    const result = await setImagesEnabled(props.projectId, changes.value.map(change => ({image_id:change.frame_id, enabled:change.enabled, version:byId.get(change.frame_id)!.version})))
    const updated = new Map(result.map(image => [image.id, image]))
    images.value = images.value.map(image => ({...image, ...(updated.get(image.id) ?? {})}))
    baseline.value = {...draft.value}
    emit('updated'); notify.success('图片启停状态已保存。')
  } catch (reason) {error.value = reason instanceof Error ? reason.message : '保存失败，草稿已保留'}
  finally {saving.value = false}
}
async function requestClose() {
  if (saving.value) return
  if (changes.value.length) {
    try {
      await ElMessageBox.confirm(`还有 ${changes.value.length} 项启停修改未保存，确定放弃吗？`, '放弃未保存修改', {type:'warning', confirmButtonText:'放弃修改', cancelButtonText:'继续筛选'})
    } catch {return}
  }
  emit('update:modelValue', false)
}
function onKey(event: KeyboardEvent) {
  if (!props.modelValue || previewOpen.value || patternOpen.value) return
  if (event.key === 'Escape') {event.preventDefault(); void requestClose()}
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {event.preventDefault(); void save()}
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => {generation++; window.removeEventListener('keydown', onKey)})
</script>

<template>
  <el-dialog append-to-body fullscreen class="image-screening-dialog" :model-value="modelValue" :show-close="false" :close-on-click-modal="false" :close-on-press-escape="false">
    <template #header><header class="screen-header vdw-dark"><span>VDM / IMAGES</span><strong :title="projectName">{{ projectName }} · 图像筛选</strong><VButton variant="quiet" icon-only label="关闭图像筛选工作台" :disabled="saving" @click="requestClose"><template #icon><el-icon><Close /></el-icon></template></VButton></header></template>
    <main class="image-screening vdw-dark">
      <section class="screen-toolbar">
        <label>每页<el-select v-model="pageSize" aria-label="筛选每页图片数"><el-option v-for="size in [50,100,200]" :key="size" :value="size" :label="String(size)"/></el-select></label>
        <label>缩略图标注<el-switch v-model="showAnnotations" aria-label="筛选缩略图标注"/></label>
        <label class="screen-scale">缩略图大小<el-slider v-model="tileSize" :min="160" :max="320" :step="20" aria-label="筛选缩略图大小"/></label>
        <VButton :disabled="!editable" :aria-pressed="rangeMode" @click="rangeMode=!rangeMode; selected=new Set(); anchor=null">{{ rangeMode ? '退出多选' : '范围多选' }}</VButton>
        <template v-if="rangeMode"><VButton :disabled="!editable || !selected.size" @click="setSelected(true)">批量启用</VButton><VButton :disabled="!editable || !selected.size" @click="setSelected(false)">批量停用</VButton></template>
        <VButton :disabled="!editable || (rangeMode && !selected.size)" @click="patternOpen=true">启停模板</VButton>
        <VButton :disabled="!editable || (rangeMode && !selected.size)" @click="byAnnotations">按标注启停</VButton>
        <VButton class="save-screening" variant="primary" :disabled="!editable || !changes.length" :loading="saving" @click="save">保存更改</VButton>
      </section>
      <section class="screen-stats" aria-label="图像筛选统计"><span>当前范围 <strong>{{ images.length }}</strong> 张</span><span>启用 {{ enabledCount }}</span><span>停用 {{ images.length-enabledCount }}</span><span>有目标 {{ positiveCount }}</span><span>无目标 {{ images.length-positiveCount }}</span><span>已选 {{ selected.size }}</span><span role="status">{{ changes.length }} 项待保存</span></section>
      <div v-if="locked" class="screen-message">项目有数据任务正在执行，启停草稿保留，任务结束后可保存。</div>
      <div v-if="error" class="screen-message" role="alert">{{ error }}<VButton v-if="!images.length" @click="load">重试加载</VButton></div>
      <section class="screen-grid-shell" :aria-busy="loading">
        <p v-if="loading" role="status">正在加载图片 {{ loadedCount }} / {{ expectedCount }}…</p>
        <p v-else-if="!images.length && !error">当前范围没有图片。</p>
        <div class="screen-grid" :style="{'--screen-tile-size':`${tileSize}px`}">
          <article v-for="image in visible" :key="image.id" class="screen-card" :class="{selected:selected.has(image.id)}">
            <button class="screen-thumbnail" :aria-label="`${rangeMode ? '选择' : '预览'} ${image.file_name}`" :aria-pressed="rangeMode ? selected.has(image.id) : undefined" @click="openImage(image,$event.shiftKey)"><FrameAnnotationThumbnail :image-url="imageThumbnailUrl(projectId,image.id)" :image-width="image.width" :image-height="image.height" :annotations="showAnnotations ? image.annotations : []" :label-colors="labelColors" :disabled="!draft[image.id]"/><span v-if="rangeMode && selected.has(image.id)" class="screen-selection" aria-hidden="true">已选</span></button>
            <footer><span :title="image.file_name">{{ image.file_name }}</span><VButton size="sm" :disabled="!editable" @click="toggle(image)">{{ draft[image.id] ? '停用' : '启用' }}</VButton></footer>
          </article>
        </div>
      </section>
      <footer class="screen-pagination"><el-pagination v-model:current-page="page" :page-size="pageSize" :total="images.length" layout="total, prev, pager, next"/></footer>
    </main>
  </el-dialog>
  <ImagePreviewDialog v-model="previewOpen" :project-id="projectId" :image="previewImage" :directory-name="directories.find(directory=>directory.id===previewImage?.directory_id)?.name ?? ''" :label-colors="labelColors" :can-edit="editable" :locked="locked || saving" :show-annotation-action="false" @enabled="toggle"/>
  <el-dialog v-model="patternOpen" append-to-body title="启停模板" width="540px"><p>按当前范围的图片顺序循环应用；范围多选时仅作用于选中图片，保存更改后生效。</p><label>模板长度<el-input-number v-model="patternLength" :min="1" :max="20"/></label><div class="screen-pattern"><el-checkbox v-for="(_,index) in pattern" :key="index" v-model="pattern[index]">第 {{ index+1 }} 张启用</el-checkbox></div><template #footer><VButton @click="patternOpen=false">取消</VButton><VButton variant="primary" :disabled="!editable" @click="applyPattern">应用草稿</VButton></template></el-dialog>
</template>

<style scoped>
:global(.image-screening-dialog.el-dialog){padding:0;background:var(--vdw-focus-canvas)}
:global(.image-screening-dialog .el-dialog__header){padding:0;margin:0}
:global(.image-screening-dialog .el-dialog__body){padding:0;height:calc(100dvh - 52px)}
.screen-header{height:52px;display:flex;align-items:center;gap:20px;padding:0 18px;background:var(--vdw-focus-panel);color:var(--vdw-focus-ink);border-bottom:1px solid var(--vdw-focus-line)}
.screen-header>span{font:700 14px var(--vdw-mono);color:var(--vdw-focus-accent)}.screen-header>strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.screen-header>.vdw-btn{margin-left:auto}
.image-screening{height:100%;display:flex;flex-direction:column;background:var(--vdw-focus-canvas);color:var(--vdw-focus-ink)}
.screen-toolbar{display:flex;align-items:center;gap:12px;padding:12px 18px;background:var(--vdw-focus-panel);border-bottom:1px solid var(--vdw-focus-line)}
.screen-toolbar label{display:flex;align-items:center;gap:8px;white-space:nowrap}.screen-toolbar .el-select{width:90px}.screen-scale .el-slider{width:100px}.save-screening{margin-left:auto}
.screen-toolbar :deep(.el-select__wrapper){background:var(--vdw-focus-panel-2);box-shadow:0 0 0 1px var(--vdw-focus-line) inset}.screen-toolbar :deep(.el-select__selected-item){color:var(--vdw-focus-ink)}
.screen-stats{display:flex;gap:24px;padding:12px 18px;background:var(--vdw-focus-panel-2);font-size:14px}.screen-stats [role=status]{margin-left:auto;color:var(--vdw-focus-accent)}
.screen-grid-shell{flex:1;min-height:0;overflow:auto;padding:18px}.screen-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(var(--screen-tile-size),1fr));gap:14px;align-content:start}
.screen-card{min-width:0;overflow:hidden;background:var(--vdw-focus-panel);border:1px solid var(--vdw-focus-line);border-radius:var(--vdw-radius-card)}.screen-card.selected{border-color:var(--vdw-focus-accent)}
.screen-card:hover{border-color:var(--vdw-focus-accent)}
.screen-thumbnail{position:relative;display:block;width:100%;padding:0;border:0;background:transparent;cursor:pointer}.screen-selection{position:absolute;top:8px;right:8px;padding:2px 6px;border:1px solid var(--vdw-focus-accent);border-radius:3px;background:var(--vdw-focus-panel);color:var(--vdw-focus-ink);font-size:13px}.screen-card footer{display:flex;align-items:center;gap:8px;padding:8px}.screen-card footer>span{flex:1;min-width:0;line-height:1.25;font-size:14px;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.screen-thumbnail:focus-visible{outline:2px solid var(--vdw-focus-accent);outline-offset:-2px}
.screen-pagination{padding:10px 18px;background:var(--vdw-focus-panel);border-top:1px solid var(--vdw-focus-line)}.screen-message{padding:12px 18px;display:flex;align-items:center;gap:16px;background:var(--vdw-focus-panel-2);color:var(--vdw-focus-ink)}
.screen-pagination :deep(.el-pagination){--el-text-color-regular:var(--vdw-focus-ink-2);--el-pagination-text-color:var(--vdw-focus-ink-2);--el-pagination-bg-color:var(--vdw-focus-panel-2);--el-pagination-button-color:var(--vdw-focus-ink-2);--el-pagination-hover-color:var(--vdw-focus-accent)}
.screen-pattern{display:flex;flex-wrap:wrap;gap:12px;margin-top:16px}
</style>
