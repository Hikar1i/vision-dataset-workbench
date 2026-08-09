<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getInferenceModel, listModelProjects, modelDownloadUrl, updateInferenceModel, type InferenceModel, type ModelProject } from '../api/models'
import PageHeader from '../components/PageHeader.vue'

const route = useRoute(); const modelId = String(route.params.modelId)
const model = ref<InferenceModel>(); const projects = ref<ModelProject[]>([]); const editing = ref(false); const saving = ref(false); const error = ref('')
const name = ref(''); const description = ref(''); const targetProjectId = ref('')
const movableProjects = computed(() => projects.value.filter((item) => item.series_type === 'archive' && item.can_manage && !item.system_key))

async function load() { try { [model.value, projects.value] = await Promise.all([getInferenceModel(modelId), listModelProjects()]) } catch (reason) { error.value = reason instanceof Error ? reason.message : '模型详情加载失败' } }
function edit() { if (!model.value) return; name.value = model.value.name; description.value = model.value.description; targetProjectId.value = model.value.model_project_id; editing.value = true }
async function save() { if (!model.value || !name.value.trim()) return; saving.value = true; try { model.value = await updateInferenceModel(modelId, name.value, description.value, model.value.version, targetProjectId.value); editing.value = false; ElMessage.success('模型信息已更新。') } catch (reason) { ElMessage.error(reason instanceof Error ? reason.message : '模型更新失败') } finally { saving.value = false } }
onMounted(load)
</script>

<template>
  <main class="content-page model-page"><PageHeader :title="model?.name || '模型详情'" :back-to="`/model-projects/${route.params.id}`" back-label="返回模型列表"><template v-if="model" #meta><el-tag effect="plain">{{ model.status }}</el-tag></template><template #actions><div class="toolbar-actions"><el-button v-if="model?.status === 'ready'" tag="a" :href="modelDownloadUrl(model.id)">下载模型</el-button><el-button v-if="model?.can_manage" type="primary" @click="edit">编辑模型</el-button></div></template></PageHeader><div class="content-body"><el-alert v-if="error" :title="error" type="error" :closable="false" /><section v-if="model" class="detail-grid"><div><span>模型 code</span><code>{{ model.model_code }}</code></div><div><span>状态</span><strong>{{ model.status }}</strong></div><div><span>创建时间</span><strong>{{ model.created_at.slice(0,16).replace('T',' ') }}</strong></div><div><span>更新时间</span><strong>{{ model.updated_at.slice(0,16).replace('T',' ') }}</strong></div><div><span>文件大小</span><strong>{{ model.file_size == null ? '—' : `${(model.file_size / 1024 / 1024).toFixed(2)} MB` }}</strong></div><div><span>SHA-256</span><code>{{ model.sha256 || '—' }}</code></div><div><span>来源文件</span><strong>{{ model.source_name }}</strong></div><div><span>存储路径</span><code>{{ model.storage_path || '—' }}</code></div><article><span>描述</span><p>{{ model.description || '暂无描述' }}</p></article><article><span>参数信息</span><pre>{{ JSON.stringify(model.parameters, null, 2) }}</pre></article></section></div><el-dialog v-model="editing" title="编辑模型" width="560px"><el-form label-position="top"><el-form-item label="模型名称"><el-input v-model="name" maxlength="128" /></el-form-item><el-form-item label="描述"><el-input v-model="description" type="textarea" :rows="3" maxlength="2000" /></el-form-item><el-form-item label="所属归档项目"><el-select v-model="targetProjectId" style="width:100%"><el-option v-for="project in movableProjects" :key="project.id" :label="project.name" :value="project.id" /></el-select></el-form-item></el-form><template #footer><el-button @click="editing=false">取消</el-button><el-button type="primary" :loading="saving" :disabled="!name.trim()" @click="save">保存更改</el-button></template></el-dialog>
  </main>
</template>

<style scoped>
.model-page{color:var(--vdw-ink);background:var(--vdw-canvas)}.toolbar-actions{display:flex;gap:10px}.detail-grid{margin-top:24px;padding:1px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;overflow:hidden;background:var(--vdw-rule);border:1px solid var(--vdw-rule);border-radius:var(--vdm-radius-card)}.detail-grid>div,.detail-grid>article{padding:20px;background:var(--vdw-surface-raised);min-width:0}.detail-grid span{display:block;margin-bottom:8px;color:var(--vdw-muted);font-size:14px}.detail-grid code{overflow-wrap:anywhere;color:var(--vdw-info);font-family:var(--vdw-mono)}.detail-grid article{grid-column:1/-1}.detail-grid p{margin:0}.detail-grid pre{max-height:360px;margin:0;padding:16px;overflow:auto;color:var(--vdw-focus-ink);background:var(--vdw-focus-canvas);border-radius:var(--vdm-radius-control)}
</style>
