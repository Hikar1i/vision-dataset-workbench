<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ImageAsset } from '../api/images'
import { imageFileUrl } from '../api/images'
import FrameAnnotationThumbnail from './FrameAnnotationThumbnail.vue'
import VButton from '../ui/VButton.vue'
const props = withDefaults(defineProps<{modelValue: boolean; projectId: string; image: ImageAsset | null; directoryName: string; labelColors: Record<string, string>; canEdit: boolean; locked: boolean; showAnnotationAction?: boolean}>(), {showAnnotationAction:true})
const emit = defineEmits<{'update:modelValue': [boolean]; annotate: [ImageAsset]; enabled: [ImageAsset, boolean]}>()
const showBoxes = ref(true)
const failed = ref(false)
watch(() => props.image?.id, () => {failed.value = false})
const dimensions = computed(() => props.image ? `${props.image.width} × ${props.image.height}` : '')
</script>
<template>
  <el-dialog append-to-body :model-value="modelValue" title="图片预览" top="8vh" width="min(1400px, 86vw)" @update:model-value="emit('update:modelValue', $event)">
    <section v-if="image" class="image-preview vdw-dark">
      <div class="preview-canvas"><FrameAnnotationThumbnail :image-url="imageFileUrl(projectId, image.id)" :image-width="image.width" :image-height="image.height" :annotations="showBoxes ? image.annotations : []" :label-colors="labelColors" :disabled="!image.enabled" @load-error="failed=true" />
        <p v-if="failed">图片加载失败，请关闭后刷新重试。</p>
      </div>
      <aside><h3>{{ image.file_name }}</h3><dl><dt>目录</dt><dd>{{ directoryName }}</dd><dt>来源路径</dt><dd>{{ image.source_relative_path }}</dd><dt>尺寸</dt><dd>{{ dimensions }}</dd><dt>大小</dt><dd>{{ (image.file_size/1024).toFixed(1) }} KB</dd><dt>标注</dt><dd>{{ image.annotations.length ? `${new Set(image.annotations.map(item=>item.label_id)).size} 类 · ${image.annotations.length} 目标` : '无目标框' }}</dd><dt>导入方式</dt><dd>{{ image.materialization }}</dd></dl>
        <el-checkbox v-model="showBoxes">显示标注框</el-checkbox>
        <VButton :disabled="!canEdit || locked" @click="emit('enabled', image, !image.enabled)">{{ image.enabled ? '停用图片' : '启用图片' }}</VButton>
        <VButton v-if="showAnnotationAction" variant="primary" :disabled="!canEdit || locked" @click="emit('annotate', image)">打开标注工作台</VButton>
      </aside>
    </section>
  </el-dialog>
</template>
<style scoped>
.image-preview{display:grid;grid-template-columns:minmax(0,1fr) 280px;height:min(680px,calc(84dvh - 100px));min-height:0;overflow:hidden;background:var(--vdw-focus-canvas);color:var(--vdw-focus-ink)}.preview-canvas{display:flex;align-items:center;justify-content:center;min-width:0;min-height:0;overflow:hidden;padding:20px}.preview-canvas :deep(.frame-thumbnail){width:100%;height:100%;max-width:900px;aspect-ratio:auto}aside{min-height:0;overflow-y:auto;background:var(--vdw-focus-panel);padding:20px;display:flex;flex-direction:column;gap:16px}h3{margin:0;overflow-wrap:anywhere}dl{margin:0;display:grid;grid-template-columns:70px 1fr;gap:10px}dt{color:var(--vdw-focus-ink-2)}dd{margin:0;overflow-wrap:anywhere}
aside>*{flex-shrink:0}aside :deep(.el-checkbox__label),aside :deep(.el-checkbox.is-checked .el-checkbox__label){color:var(--vdw-focus-ink)}
</style>
