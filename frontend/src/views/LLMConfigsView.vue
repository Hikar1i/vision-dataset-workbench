<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import {
  createLLMConfig, deleteLLMConfig, getLLMDefaults, listLLMConfigs, saveLLMDefaults,
  testLLMConfig, updateLLMConfig, type LLMConfig,
} from '../api/llm'

const configs = ref<LLMConfig[]>([])
const defaults = reactive<Record<string, unknown>>({})
const editing = ref<LLMConfig | null>(null)
const dialog = ref(false)
const advanced = ref(false)
const saving = ref(false)
const form = reactive({ name: '', description: '', base_url: '', api_type: 'openai', model_name: '', api_key: '', enabled: true, advanced_options: {} as Record<string, unknown> })

async function load() { configs.value = await listLLMConfigs(); Object.assign(defaults, await getLLMDefaults()) }
function openCreate() { editing.value = null; Object.assign(form, { name: '', description: '', base_url: '', api_type: 'openai', model_name: '', api_key: '', enabled: true, advanced_options: { ...defaults } }); dialog.value = true }
function openEdit(item: LLMConfig) { editing.value = item; Object.assign(form, { ...item, api_key: '', advanced_options: { ...defaults, ...item.advanced_options } }); dialog.value = true }
async function save() {
  saving.value = true
  try {
    const payload = { ...form, advanced_options: form.advanced_options, ...(form.api_key ? { api_key: form.api_key } : {}) }
    const result = editing.value ? await updateLLMConfig(editing.value.id, payload) : await createLLMConfig(payload)
    const index = configs.value.findIndex((item) => item.id === result.id)
    if (index >= 0) configs.value[index] = result; else configs.value.unshift(result)
    dialog.value = false; ElMessage.success('大模型配置已保存')
  } catch (reason) { ElMessage.error(reason instanceof Error ? reason.message : '保存失败') }
  finally { saving.value = false }
}
async function test(item: LLMConfig) {
  try {
    const result = await testLLMConfig(item.id)
    item.available = result.available; item.last_test_status = result.status as LLMConfig['last_test_status']; item.last_test_latency_ms = result.latency_ms
    ElMessage[result.available ? 'success' : 'error'](result.available ? '连接成功，' + result.latency_ms + ' ms' : '连接失败')
  } catch (reason) { ElMessage.error(reason instanceof Error ? reason.message : '测试失败') }
}
async function remove(item: LLMConfig) { await ElMessageBox.confirm('删除配置“' + item.name + '”？', '确认删除'); await deleteLLMConfig(item.id); configs.value = configs.value.filter((value) => value.id !== item.id) }
async function saveDefaultOptions() { Object.assign(defaults, await saveLLMDefaults(defaults)); ElMessage.success('默认设置已保存') }
onMounted(() => void load())
</script>

<template>
  <main class="content-page llm-page">
    <header class="content-toolbar"><div class="content-toolbar-title"><h1>大模型配置</h1><span>仅当前用户可见</span></div><el-button type="primary" @click="openCreate">新增配置</el-button></header>
    <el-tabs>
      <el-tab-pane label="配置列表">
        <div class="llm-grid">
          <el-card v-for="item in configs" :key="item.id" :class="{ unavailable: !item.available }">
            <template #header><div class="card-title"><strong>{{ item.name }}</strong><el-tag :type="item.enabled ? 'success' : 'info'">{{ item.enabled ? '启用' : '停用' }}</el-tag></div></template>
            <p>{{ item.base_url }}</p><p>{{ item.api_type }} · {{ item.model_name }}</p><p>连接：{{ item.last_test_status }}<span v-if="item.last_test_latency_ms"> · {{ item.last_test_latency_ms }} ms</span></p>
            <div class="card-actions"><el-button size="small" @click="test(item)">测试连接</el-button><el-button size="small" @click="openEdit(item)">编辑</el-button><el-button size="small" type="danger" @click="remove(item)">删除</el-button></div>
          </el-card>
          <el-empty v-if="!configs.length" description="还没有大模型配置" />
        </div>
      </el-tab-pane>
      <el-tab-pane label="大模型默认设置">
        <el-form class="defaults-form" label-position="top"><el-form-item v-for="(_, key) in defaults" :key="key" :label="String(key)"><el-input-number v-model="defaults[key] as number" :min="0" :controls="false" /></el-form-item></el-form>
        <el-button type="primary" @click="saveDefaultOptions">保存默认设置</el-button>
      </el-tab-pane>
    </el-tabs>
    <el-dialog v-model="dialog" :title="editing ? '编辑大模型配置' : '新增大模型配置'" width="560px">
      <el-form label-position="top">
        <el-form-item label="配置名称"><el-input v-model="form.name" /></el-form-item><el-form-item label="描述"><el-input v-model="form.description" type="textarea" /></el-form-item><el-form-item label="Base URL"><el-input v-model="form.base_url" placeholder="http://localhost:8444/v1" /></el-form-item>
        <el-form-item label="API 类型"><el-select v-model="form.api_type"><el-option label="OpenAI-compatible" value="openai" /><el-option label="Anthropic" value="anthropic" /></el-select></el-form-item><el-form-item label="模型名"><el-input v-model="form.model_name" /></el-form-item><el-form-item label="API Key"><el-input v-model="form.api_key" type="password" show-password placeholder="留空表示保持原值" /></el-form-item>
        <el-checkbox v-model="form.enabled">启用</el-checkbox> <el-button text @click="advanced = !advanced">{{ advanced ? '收起高级选项' : '展开高级选项' }}</el-button>
        <div v-if="advanced" class="advanced-options"><el-form-item v-for="(_, key) in form.advanced_options" :key="key" :label="String(key)"><el-input-number v-model="form.advanced_options[key] as number" :min="0" :controls="false" /></el-form-item></div>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving" :disabled="!form.name || !form.base_url || !form.model_name" @click="save">保存</el-button></template>
    </el-dialog>
  </main>
</template>

<style scoped>
.llm-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.llm-grid .unavailable { border-color: var(--el-color-danger); }
.card-title, .card-actions { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.defaults-form, .advanced-options { display: grid; grid-template-columns: repeat(3, minmax(160px, 1fr)); gap: 12px; }
</style>
