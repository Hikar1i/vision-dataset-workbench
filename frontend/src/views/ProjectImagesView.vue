<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { Aim, Delete, Download, Filter, Search, Upload } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { can } from '../api/access'
import type { Project } from '../api/projects'
import { deleteImages, listImageDirectories, listImages, imageThumbnailUrl, setImagesEnabled, setImagesEnabledByAnnotations, type ImageAsset, type ImageDirectory, type ImageFilters } from '../api/images'
import { listTasks, type ProjectTask } from '../api/media'
import { listLabels, type ProjectLabel } from '../api/labels'
import ImportImagesDialog from '../components/ImportImagesDialog.vue'
import ImagePreviewDialog from '../components/ImagePreviewDialog.vue'
import ImageScreeningDialog from '../components/ImageScreeningDialog.vue'
import ExportDatasetDialog from '../components/ExportDatasetDialog.vue'
import BatchAnnotationDialog from '../components/BatchAnnotationDialog.vue'
import FrameAnnotationThumbnail from '../components/FrameAnnotationThumbnail.vue'
import VButton from '../ui/VButton.vue'
import VTag from '../ui/VTag.vue'
import { imageAnnotationStatus } from '../ui/status'
import { useProjectHeaderHost } from '../ui/projectHeaderHost'
import { notify } from '../ui/notify'
const props = defineProps<{project: Project}>()
const route = useRoute(), router = useRouter()
const headerHost = useProjectHeaderHost()
const directories = ref<ImageDirectory[]>([]), images = ref<ImageAsset[]>([]), labels = ref<ProjectLabel[]>([])
const selected = ref<string[]>([]), directoryId = ref(''), search = ref('')
const annotationStatus = ref<'' | 'pending' | 'labeled'>(''), enabledFilter = ref('all'), labelId = ref('')
const page = ref(1), pageSize = ref<50 | 100 | 200>(50), total = ref(0)
const loading = ref(false), writing = ref(false), error = ref(''), showBoxes = ref(true), tileSize = ref(200)
const importOpen = ref(false), exportOpen = ref(false), batchOpen = ref(false), previewOpen = ref(false)
const screeningOpen = ref(false)
const previewImage = ref<ImageAsset | null>(null), activeTasks = ref<ProjectTask[]>([])
const writeAllowed = computed(() => can(props.project.access, 'project.update'))
const taskAllowed = computed(() => writeAllowed.value && can(props.project.access, 'task.execute'))
const locked = computed(() => activeTasks.value.length > 0)
const selectedImages = computed(() => images.value.filter(i => selected.value.includes(i.id)))
const selectedStoppedImages = computed(() => selectedImages.value.filter(image => !image.enabled))
const colors = computed(() => Object.fromEntries(labels.value.map(l => [l.id, l.color])))
const filters = computed<ImageFilters>(() => ({directory_id: directoryId.value || undefined, search: search.value || undefined,
  annotation_status: annotationStatus.value || undefined, enabled: enabledFilter.value === 'all' ? undefined : enabledFilter.value === 'enabled', label_id: labelId.value || undefined}))
const totals = computed(() => directories.value.reduce((s, d) => ({images: s.images+d.total_images, labeled: s.labeled+d.labeled_images}), {images: 0, labeled: 0}))
let alive = true
let requestId = 0, anchor = -1, timer: ReturnType<typeof setTimeout> | undefined, poll: ReturnType<typeof setInterval> | undefined
async function load() {
  if (props.project.project_type !== 'image') return
  const request = ++requestId; loading.value = true; error.value = ''
  try {
    const [result, groups, projectLabels, tasks] = await Promise.all([listImages(props.project.id, filters.value, page.value, pageSize.value), listImageDirectories(props.project.id), listLabels(props.project.id), listTasks(props.project.id)])
    if (!alive || request !== requestId) return
    images.value = result.items; total.value = result.total; directories.value = groups; labels.value = projectLabels
    activeTasks.value = tasks.items.filter(t => ['queued','running'].includes(t.status) && ['import_images','auto_annotate','export_dataset'].includes(t.type))
    selected.value = selected.value.filter(id => images.value.some(i => i.id === id)); anchor = -1
  } catch (reason) {if (request === requestId) error.value = reason instanceof Error ? reason.message : '图片加载失败，请刷新重试'}
  finally {if (request === requestId) loading.value = false}
}
function select(index: number, shift: boolean) {
  if (shift && anchor >= 0) selected.value = [...new Set([...selected.value, ...images.value.slice(Math.min(anchor,index), Math.max(anchor,index)+1).map(i => i.id)])]
  else {
    const image = images.value[index]; if (!image) return
    selected.value = selected.value.includes(image.id) ? selected.value.filter(id => id !== image.id) : [...selected.value, image.id]
  }
  anchor = index
}
function annotate(image: ImageAsset) {
  previewOpen.value = false
  void router.push({path: `/projects/${props.project.id}/images/${image.id}/annotation`, query: Object.fromEntries(Object.entries(filters.value).filter(([,v]) => v !== undefined).map(([k,v]) => [k,String(v)])), state: {annotationFromImageList: true}})
}
async function changeEnabled(items: ImageAsset[], enabled: boolean) {
  writing.value = true
  try {await setImagesEnabled(props.project.id, items.map(i => ({image_id: i.id, version: i.version, enabled}))); previewOpen.value = false; await load()}
  catch (reason) {notify.error(reason instanceof Error ? reason.message : '图片状态保存失败')}
  finally {writing.value = false}
}
function openAnnotation() {
  const image = selectedImages.value[0] ?? images.value[0]
  if (image) annotate(image)
}
async function deleteSelected(items: ImageAsset[]) {
  const stopped = items.filter(image => !image.enabled)
  if (!stopped.length || !writeAllowed.value || locked.value || writing.value) return
  try {
    await ElMessageBox.confirm(`删除 ${stopped.length} 个停用图像？图像、缩略图和标注将移入归档，已有数据集不会改变。${items.length > stopped.length ? '选中的启用图像不会删除。' : ''}`, '删除图像', {type:'warning', confirmButtonText:'删除图像', cancelButtonText:'取消'})
  } catch {return}
  writing.value = true
  try {
    const result = await deleteImages(props.project.id, stopped.map(image => ({image_id:image.id, version:image.version})))
    selected.value = selected.value.filter(id => !result.deleted.includes(id))
    if (previewImage.value && result.deleted.includes(previewImage.value.id)) previewOpen.value = false
    if (images.value.length === result.deleted.length && page.value > 1) page.value--
    notify.success(`已删除 ${result.deleted.length} 个停用图像。`)
    await load()
  } catch(reason) {notify.error(reason instanceof Error ? reason.message : '删除图像失败')}
  finally {writing.value=false}
}
async function enableByAnnotations() {
  const items = [...selectedImages.value]
  if (!items.length || !writeAllowed.value || locked.value || writing.value) return
  try {
    await ElMessageBox.confirm(`对选中的 ${items.length} 张图片按标注启停：有目标框的启用，无目标框的停用。将覆盖这些图片当前启停状态。`, '按标注启停', {type:'warning', confirmButtonText:'应用启停', cancelButtonText:'取消'})
  } catch {return}
  writing.value = true
  try {
    await setImagesEnabledByAnnotations(props.project.id, items.map(image => ({image_id:image.id, version:image.version})))
    notify.success('已按标注更新所选图片的启停状态。')
    await load()
  } catch(reason) {notify.error(reason instanceof Error ? reason.message : '按标注启停失败')}
  finally {writing.value=false}
}
function clearFilteredSelection() {
  if (selected.value.length) notify.info('筛选已变化，已清空当前页选择。')
  selected.value=[]; anchor=-1; page.value=1
}
watch([directoryId, annotationStatus, enabledFilter, labelId, pageSize], () => {clearFilteredSelection(); void load()})
watch(search, () => {requestId++; clearFilteredSelection(); if(timer)clearTimeout(timer); timer=setTimeout(load,250)})
watch(() => route.name, name => {if(name === 'project-images') void load()})
function clearFilters() {
  directoryId.value=''; search.value=''; annotationStatus.value=''; enabledFilter.value='all'; labelId.value=''
}
const hasFilters = computed(() => Object.values(filters.value).some(value => value !== undefined))
async function pollTasks() {
  if (!alive || route.params.imageId || writing.value) return
  try {
    const result = await listTasks(props.project.id)
    if (!alive) return
    const current = result.items.filter(t => ['queued','running'].includes(t.status) && ['import_images','auto_annotate','export_dataset'].includes(t.type))
    const changed = current.map(t=>t.id).join() !== activeTasks.value.map(t=>t.id).join()
    activeTasks.value = current
    if (changed) await load()
  } catch { /* Keep the last known write lock until a successful refresh. */ }
}
onMounted(() => {
  void load(); window.addEventListener('vdm:tasks-settled', load)
  poll=setInterval(pollTasks,5000)
})
onUnmounted(() => {alive=false;requestId++; if(timer)clearTimeout(timer); if(poll)clearInterval(poll); window.removeEventListener('vdm:tasks-settled', load)})
</script>
<template>
  <main class="image-project-page">
  <Teleport defer to="#project-page-meta" :disabled="!headerHost"><span>{{ directories.length }} 个目录 · {{ totals.images }} 张图片 · {{ totals.labeled }} 张已标注</span></Teleport>
  <div class="content-body image-body">
    <section class="image-action-lane" data-test="image-action-lane">
      <div class="image-primary-actions">
        <VButton :disabled="!images.length || loading" @click="openAnnotation"><template #icon><el-icon><Aim /></el-icon></template>标注</VButton>
        <VButton :disabled="!directories.length || loading" @click="screeningOpen=true"><template #icon><el-icon><Filter /></el-icon></template>筛选</VButton>
      </div>
      <div class="image-toolbar-actions" data-test="image-toolbar-actions">
        <el-checkbox aria-label="当前页全选" :model-value="images.length>0 && selected.length===images.length" :indeterminate="selected.length>0 && selected.length<images.length" @change="(value: boolean) => selected=value ? images.map(i=>i.id) : []">当前页全选</el-checkbox>
        <el-input v-model="search" class="image-search" :prefix-icon="Search" clearable placeholder="搜索文件名" aria-label="搜索文件名" />
        <template v-if="selected.length">
          <VButton variant="danger" :disabled="!writeAllowed || locked || writing || !selectedStoppedImages.length" :title="selectedStoppedImages.length ? '仅删除选中的停用图像' : '请先停用图像再删除'" @click="deleteSelected(selectedImages)">删除 {{ selectedStoppedImages.length }} 个图像</VButton>
          <VButton :disabled="!writeAllowed || locked || writing" @click="enableByAnnotations">按标注启停</VButton>
          <VButton :disabled="!taskAllowed || locked || writing" @click="batchOpen=true">批量自动标注</VButton>
          <VButton :disabled="!writeAllowed || locked || writing" @click="changeEnabled(selectedImages,false)">批量停用</VButton>
          <VButton :disabled="!writeAllowed || locked || writing" @click="changeEnabled(selectedImages,true)">批量启用</VButton>
        </template>
        <template v-else>
          <VButton :disabled="!taskAllowed || locked || writing" @click="exportOpen=true"><template #icon><el-icon><Download /></el-icon></template>导出数据集</VButton>
          <VButton variant="primary" :disabled="!taskAllowed || locked || writing" @click="importOpen=true"><template #icon><el-icon><Upload /></el-icon></template>导入图像目录</VButton>
        </template>
      </div>
    </section>
    <el-alert v-if="locked" title="图片数据任务正在处理，暂时不能修改图片、标签或创建新的数据任务。可在任务中心查看或取消。" type="info" :closable="false" />
    <div v-if="error" class="image-error"><el-alert :title="error" type="error" :closable="false" /><VButton :loading="loading" @click="load">重试加载</VButton></div>
    <div class="image-workspace">
      <aside class="directory-list" aria-label="图片目录">
        <button :class="{active:!directoryId}" @click="directoryId=''">全部目录 <span>{{ totals.images }}</span></button>
        <div v-for="directory in directories" :key="directory.id"><button :class="{active:directoryId===directory.id}" :title="directory.source_relative_path" @click="directoryId=directory.id"><span class="directory-name" :title="directory.name">{{ directory.name }}</span><span class="directory-count">{{ directory.total_images }}</span></button>
          <details><summary>来源与状态</summary><p>{{ directory.source_relative_path }}</p><p>启用 {{ directory.enabled_images }} · 已标注 {{ directory.labeled_images }}</p><p>宽 {{ directory.min_width }}–{{ directory.max_width }}，高 {{ directory.min_height }}–{{ directory.max_height }} px</p></details>
        </div>
      </aside>
      <section class="images-main" v-loading="loading">
        <div class="image-filters">
          <el-select v-model="annotationStatus" class="status-filter" placeholder="全部标注" aria-label="标注状态"><el-option value="" label="全部标注"/><el-option value="pending" label="待标注"/><el-option value="labeled" label="已标注"/></el-select>
          <el-select v-model="enabledFilter" class="status-filter" aria-label="启用状态"><el-option value="all" label="全部启停"/><el-option value="enabled" label="已启用"/><el-option value="disabled" label="已停用"/></el-select>
          <el-select v-model="labelId" clearable placeholder="全部类别" aria-label="筛选类别"><el-option v-for="label in labels" :key="label.id" :value="label.id" :label="label.name"/></el-select>
          <label class="annotation-switch">缩略图标注<el-switch v-model="showBoxes" aria-label="缩略图标注" /></label>
          <label>缩略图 <el-slider v-model="tileSize" :min="160" :max="320" :step="20" aria-label="缩略图大小"/></label>
        </div>
        <div class="image-grid" :style="{'--tile-size': `${tileSize}px`}">
          <article v-for="(image,index) in images" :key="image.id" class="image-card" :class="{selected:selected.includes(image.id)}">
            <button class="image-open" :aria-label="`预览 ${image.file_name}`" @click="previewImage=image;previewOpen=true"><FrameAnnotationThumbnail :image-url="imageThumbnailUrl(project.id,image.id)" :image-width="image.width" :image-height="image.height" :annotations="showBoxes ? image.annotations : []" :label-colors="colors" :disabled="!image.enabled"/></button>
            <div class="image-caption"><input type="checkbox" :checked="selected.includes(image.id)" :aria-label="`选择 ${image.file_name}`" @click="select(index,$event.shiftKey)"/><strong :title="image.file_name">{{ image.file_name }}</strong><VButton size="sm" variant="quiet" :disabled="!writeAllowed || locked || writing" :aria-label="`${image.enabled ? '停用' : '启用'} ${image.file_name}`" @click="changeEnabled([image],!image.enabled)">{{ image.enabled ? '停用' : '启用' }}</VButton></div>
            <footer><VTag :tone="imageAnnotationStatus(image.annotation_status).tone">{{ imageAnnotationStatus(image.annotation_status).label }}</VTag><span>{{ new Set(image.annotations.map(a=>a.label_id)).size }} 类 · {{ image.annotations.length }} 目标</span></footer>
            <div class="image-source"><small :title="directories.find(d=>d.id===image.directory_id)?.name">{{ directories.find(d=>d.id===image.directory_id)?.name }}</small><VButton size="sm" variant="danger" icon-only :label="`删除图像 ${image.file_name}`" :title="image.enabled ? '请先停用图像再删除' : '删除图像'" :disabled="image.enabled || !writeAllowed || locked || writing" @click="deleteSelected([image])"><template #icon><el-icon><Delete /></el-icon></template></VButton></div>
          </article>
        </div>
        <el-empty v-if="!loading && !error && !images.length" :description="directories.length ? '没有匹配的图片，请调整筛选条件' : '请导入图像目录或 YOLO 目标检测数据集'"><VButton v-if="hasFilters" @click="clearFilters">清除筛选</VButton></el-empty>
        <el-pagination :current-page="page" v-model:page-size="pageSize" :page-sizes="[50,100,200]" :total="total" layout="total, sizes, prev, pager, next" @current-change="(value: number)=>{page=value;selected=[];load()}"/>
      </section>
    </div>
  </div>
  <ImportImagesDialog v-model="importOpen" :project-id="project.id" @submitted="load"/>
  <ExportDatasetDialog v-model="exportOpen" :project-id="project.id" @submitted="load" @source-updated="load"/>
  <BatchAnnotationDialog v-model="batchOpen" :project-id="project.id" :images="selectedImages" scope="all" @submitted="load"/>
  <ImagePreviewDialog v-model="previewOpen" :project-id="project.id" :image="previewImage" :directory-name="directories.find(d=>d.id===previewImage?.directory_id)?.name ?? ''" :label-colors="colors" :can-edit="taskAllowed" :locked="locked" @annotate="annotate" @enabled="(image,value)=>changeEnabled([image],value)"/>
  <ImageScreeningDialog v-model="screeningOpen" :project-id="project.id" :project-name="project.name" :filters="filters" :directories="directories" :can-edit="writeAllowed" :locked="locked" :label-colors="colors" @updated="load"/>
  <RouterView/>
  </main>
</template>
<style scoped>
.image-body{display:grid;gap:14px}
.image-action-lane{display:flex;align-items:center;gap:13px;min-height:52px;padding:0 9px;border-bottom:1px solid var(--vdw-line)}
.image-primary-actions,.image-toolbar-actions{display:flex;align-items:center;gap:8px}
.image-toolbar-actions{margin-left:auto;min-width:0}.image-search{width:240px}
.image-toolbar-actions .el-checkbox{white-space:nowrap}.image-error{display:flex;align-items:center;gap:12px}
.image-filters{display:flex;align-items:center;gap:12px}
.image-workspace{display:grid;grid-template-columns:220px minmax(0,1fr);border:1px solid var(--vdw-line);background:var(--vdw-surface)}
.directory-list{padding:12px;background:var(--vdw-surface-2);border-right:1px solid var(--vdw-line)}
.directory-list button{display:flex;justify-content:space-between;gap:8px;width:100%;padding:12px;color:var(--vdw-ink);text-align:left;overflow-wrap:anywhere;border:1px solid transparent;background:transparent;cursor:pointer}
.directory-list button:hover,.directory-list button.active{background:var(--vdw-accent-soft);border-color:var(--vdw-accent);color:var(--vdw-accent)}
.directory-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.directory-count{flex:none;white-space:nowrap}
details{padding:0 12px 10px;font-size:13px;color:var(--vdw-ink-2);overflow-wrap:anywhere}
summary{cursor:pointer}
.images-main{min-width:0;padding:16px;display:grid;gap:16px}
.image-filters .el-select{width:145px}.image-filters .status-filter{width:120px}
.image-filters>label{display:flex;gap:12px;align-items:center;white-space:nowrap}.image-filters>label:last-child{margin-left:auto}
.image-filters .el-slider{width:110px}
.image-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(var(--tile-size),1fr));gap:12px;align-content:start}
.image-card{min-width:0;overflow:hidden;border:1px solid var(--vdw-line);border-radius:7px;background:var(--vdw-surface-3)}
.image-card.selected,.image-card:hover{border-color:var(--vdw-accent)}
.image-open{width:100%;padding:0;border:0;cursor:pointer;background:transparent}
.image-caption{display:flex;gap:6px;align-items:center;padding:6px 8px;min-height:48px}
.image-caption input[type=checkbox]{width:14px;height:14px;margin:0;flex:none;accent-color:var(--vdw-accent)}
.image-caption strong{font-size:14px;line-height:1.25;flex:1;min-width:0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.image-caption .vdw-btn{flex:none;padding:0 4px}
.image-card footer{display:flex;align-items:center;gap:8px;padding:0 10px;font-size:13px}
.image-source{display:flex;align-items:center;gap:4px;padding:2px 8px 4px 10px}
.image-source small{flex:1;min-width:0;color:var(--vdw-ink-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
