<script setup lang="ts">
import { Connection, Delete, EditPen, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'

import {
  createLLMConfig, deleteLLMConfig, getLLMDefaults, listLLMConfigs, saveLLMDefaults,
  testLLMConfig, updateLLMConfig, type LLMConfig,
} from '../api/llm'
import PageHeader from '../components/PageHeader.vue'
import VButton from '../ui/VButton.vue'
import VCellName from '../ui/VCellName.vue'
import VChip from '../ui/VChip.vue'
import VEmpty from '../ui/VEmpty.vue'
import VField from '../ui/VField.vue'
import VPanel from '../ui/VPanel.vue'
import { isRecentRow, markRecentRowFromAction } from '../ui/recentRows'
import VRow from '../ui/VRow.vue'
import VTable from '../ui/VTable.vue'
import VTag from '../ui/VTag.vue'
import { enabledStatus } from '../ui/status'
import {
  groupedLLMOptions,
  llmOption,
  ungroupedLLMOptions,
} from './llmOptions'

type Tab = 'list' | 'defaults'

const configs = ref<LLMConfig[]>([])
const defaults = reactive<Record<string, unknown>>({})
const editing = ref<LLMConfig | null>(null)
const dialog = ref(false)
const advanced = ref(false)
const saving = ref(false)
const loading = ref(false)
const testing = ref<Record<string, boolean>>({})
const error = ref('')
const tab = ref<Tab>('list')
const form = reactive({
  name: '', description: '', base_url: '', api_type: 'openai', model_name: '',
  api_key: '', enabled: true, advanced_options: {} as Record<string, unknown>,
})

const COLUMNS = 'minmax(200px, 1.2fr) 110px minmax(160px, 0.7fr) 210px'
const RECENT_SCOPE = 'llm-configs'

const defaultGroups = computed(() => groupedLLMOptions(Object.keys(defaults)))
const extraDefaultKeys = computed(() => ungroupedLLMOptions(Object.keys(defaults)))
const advancedGroups = computed(() => groupedLLMOptions(Object.keys(form.advanced_options)))

function resetDefaults() {
  for (const key of Object.keys(defaults)) {
    defaults[key] = llmOption(key).min
  }
}

const canSave = computed(() => !!form.name && !!form.base_url && !!form.model_name)

/** 连接结果：把 status + latency 合成一句可读的话，而不是直接吐英文码 */
function connection(item: LLMConfig) {
  if (!item.last_test_status) return { text: '尚未测试', tone: 'idle' as const }
  if (item.available) {
    return {
      text: item.last_test_latency_ms ? `成功 ${item.last_test_latency_ms} ms` : '成功',
      tone: 'ok' as const,
    }
  }
  return { text: '连接失败', tone: 'danger' as const }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [items, defaultOptions] = await Promise.all([listLLMConfigs(), getLLMDefaults()])
    configs.value = items
    Object.assign(defaults, defaultOptions)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '大模型配置加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  advanced.value = false
  Object.assign(form, {
    name: '', description: '', base_url: '', api_type: 'openai', model_name: '',
    api_key: '', enabled: true, advanced_options: { ...defaults },
  })
  dialog.value = true
}

function openEdit(item: LLMConfig) {
  editing.value = item
  advanced.value = false
  Object.assign(form, {
    ...item, api_key: '', advanced_options: { ...defaults, ...item.advanced_options },
  })
  dialog.value = true
}

async function save() {
  saving.value = true
  try {
    const payload = {
      ...form,
      advanced_options: form.advanced_options,
      ...(form.api_key ? { api_key: form.api_key } : {}),
    }
    const result = editing.value
      ? await updateLLMConfig(editing.value.id, payload)
      : await createLLMConfig(payload)
    const index = configs.value.findIndex((item) => item.id === result.id)
    if (index >= 0) configs.value[index] = result
    else configs.value.unshift(result)
    dialog.value = false
    ElMessage.success('大模型配置已保存')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function test(item: LLMConfig) {
  testing.value = { ...testing.value, [item.id]: true }
  try {
    const result = await testLLMConfig(item.id)
    item.available = result.available
    item.last_test_status = result.status as LLMConfig['last_test_status']
    item.last_test_latency_ms = result.latency_ms
    ElMessage[result.available ? 'success' : 'error'](
      result.available ? `连接成功，${result.latency_ms} ms` : '连接失败',
    )
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '测试失败')
  } finally {
    testing.value = { ...testing.value, [item.id]: false }
  }
}

async function remove(item: LLMConfig) {
  try {
    await ElMessageBox.confirm(`删除配置“${item.name}”？`, '确认删除', { type: 'warning' })
  } catch {
    return
  }
  await deleteLLMConfig(item.id)
  configs.value = configs.value.filter((value) => value.id !== item.id)
  ElMessage.success('配置已删除')
}

async function saveDefaultOptions() {
  saving.value = true
  try {
    Object.assign(defaults, await saveLLMDefaults(defaults))
    ElMessage.success('默认设置已保存')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <main class="content-page">
    <PageHeader title="大模型配置" kind="llm configs">
      <template #meta>
        <span data-test="page-stat">{{ configs.length }} 个配置 · 仅当前用户可见</span>
      </template>
      <template #actions>
        <VButton data-test="llm-create" variant="primary" @click="openCreate">
          <template #icon><el-icon><Plus /></el-icon></template>
          新增配置
        </VButton>
      </template>
      <template #tabs>
        <button
          data-test="llm-tab-list"
          type="button"
          :class="{ 'is-active': tab === 'list' }"
          :aria-selected="tab === 'list'"
          @click="tab = 'list'"
        >
          配置列表 <span class="tab-count">{{ configs.length }}</span>
        </button>
        <button
          data-test="llm-tab-defaults"
          type="button"
          :class="{ 'is-active': tab === 'defaults' }"
          :aria-selected="tab === 'defaults'"
          @click="tab = 'defaults'"
        >
          默认设置
        </button>
      </template>
    </PageHeader>

    <section v-loading="loading" data-test="llm-tabs" class="content-body llm-tabs">
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

      <VPanel v-if="tab === 'list'" flush>
        <VTable
          :columns="COLUMNS"
          :headers="['配置', '状态', '连接', '操作']"
        >
          <VRow
            v-for="item in configs"
            :key="item.id"
            :columns="COLUMNS"
            :recent="isRecentRow(RECENT_SCOPE, item.id)"
          >
            <VCellName :name="item.name" :sub="`${item.base_url} · ${item.model_name}`">
              <template #after><VChip>{{ item.api_type }}</VChip></template>
            </VCellName>
            <VTag :tone="enabledStatus(item.enabled).tone">
              {{ enabledStatus(item.enabled).label }}
            </VTag>
            <span class="llm-conn" :class="`is-${connection(item).tone}`">
              {{ connection(item).text }}
            </span>
            <div
              class="row-actions"
              @click.capture="markRecentRowFromAction($event, RECENT_SCOPE, item.id)"
            >
              <VButton
                variant="quiet"
                size="sm"
                :loading="testing[item.id]"
                @click="test(item)"
              ><template #icon><el-icon><Connection /></el-icon></template>测试</VButton>
              <VButton
                :data-test="`llm-edit-${item.id}`"
                variant="quiet"
                size="sm"
                @click="openEdit(item)"
              ><template #icon><el-icon><EditPen /></el-icon></template>编辑</VButton>
              <VButton variant="danger" size="sm" @click="remove(item)"><template #icon><el-icon><Delete /></el-icon></template>删除</VButton>
            </div>
          </VRow>
          <template #empty>
            <VEmpty
              v-if="!configs.length && !error"
              data-test="llm-empty"
              class="llm-empty"
              title="还没有大模型配置"
              note="配置一个 OpenAI 兼容或 Anthropic 服务后，就能在标注页发起在线自动标注。"
            >
              <VButton variant="primary" @click="openCreate">新增配置</VButton>
            </VEmpty>
          </template>
        </VTable>
      </VPanel>

      <VPanel v-else title="默认设置">
        <template #head>
          <VChip>应用于新建配置</VChip>
        </template>

        <p class="llm-defaults__lead">
          这些值会作为新建配置的初始高级选项。已有配置不受影响，可在各自的编辑弹窗里单独覆盖。
        </p>

        <section v-for="group in defaultGroups" :key="group.key" class="llm-group">
          <header>
            <h3>{{ group.title }}</h3>
            <p>{{ group.note }}</p>
          </header>
          <div class="llm-defaults">
            <VField
              v-for="key in group.keys"
              :key="key"
              :label="llmOption(key).label"
              :hint="llmOption(key).unit
                ? `${llmOption(key).min}–${llmOption(key).max} ${llmOption(key).unit}`
                : `${llmOption(key).min}–${llmOption(key).max}`"
              :note="llmOption(key).note"
            >
              <template #default="{ id }">
                <el-input-number
                  :id="id"
                  v-model="defaults[key] as number"
                  :min="llmOption(key).min"
                  :max="llmOption(key).max"
                  :step="llmOption(key).step"
                  :precision="llmOption(key).precision"
                  :controls="false"
                />
                <code class="llm-key">{{ key }}</code>
              </template>
            </VField>
          </div>
        </section>

        <section v-if="extraDefaultKeys.length" class="llm-group">
          <header>
            <h3>其他参数</h3>
            <p>后端新增但前端尚未补充说明的参数，仍可直接编辑。</p>
          </header>
          <div class="llm-defaults">
            <VField v-for="key in extraDefaultKeys" :key="key" :label="key">
              <template #default="{ id }">
                <el-input-number
                  :id="id"
                  v-model="defaults[key] as number"
                  :min="0"
                  :controls="false"
                />
              </template>
            </VField>
          </div>
        </section>

        <template #footer>
          <VButton variant="quiet" @click="resetDefaults">全部置为最小值</VButton>
          <VButton
            variant="primary"
            class="llm-defaults__save"
            :loading="saving"
            @click="saveDefaultOptions"
          >保存默认设置</VButton>
        </template>
      </VPanel>
    </section>

    <el-dialog
      v-model="dialog"
      :title="editing ? '编辑大模型配置' : '新增大模型配置'"
      width="620px"
    >
      <div class="llm-form">
        <VField label="配置名称" required>
          <template #default="{ id }">
            <el-input :id="id" v-model="form.name" autocomplete="off" />
          </template>
        </VField>
        <VField label="模型名" required>
          <template #default="{ id }">
            <el-input :id="id" v-model="form.model_name" autocomplete="off" />
          </template>
        </VField>
        <VField label="Base URL" class="llm-form__wide" required>
          <template #default="{ id }">
            <el-input
              :id="id"
              v-model="form.base_url"
              autocomplete="off"
              placeholder="http://localhost:8444/v1"
            />
          </template>
        </VField>
        <VField label="API 类型">
          <template #default="{ id }">
            <el-select :id="id" v-model="form.api_type">
              <el-option label="OpenAI-compatible" value="openai" />
              <el-option label="Anthropic" value="anthropic" />
            </el-select>
          </template>
        </VField>
        <VField
          label="API Key"
          :note="editing?.masked_api_key ? `已保存：${editing.masked_api_key}` : undefined"
        >
          <template #default="{ id }">
            <el-input
              :id="id"
              v-model="form.api_key"
              data-test="llm-api-key"
              type="password"
              show-password
              autocomplete="new-password"
              :placeholder="editing ? '留空表示保持现有 API Key' : '无密钥服务可留空'"
            />
          </template>
        </VField>
        <VField label="描述" class="llm-form__wide">
          <template #default="{ id }">
            <el-input :id="id" v-model="form.description" type="textarea" :rows="2" />
          </template>
        </VField>
      </div>

      <div class="llm-form__row">
        <el-checkbox v-model="form.enabled">启用此配置</el-checkbox>
        <VButton
          data-test="llm-advanced-toggle"
          variant="quiet"
          size="sm"
          aria-controls="llm-advanced-options"
          :aria-expanded="advanced"
          @click="advanced = !advanced"
        >{{ advanced ? '收起高级选项' : '展开高级选项' }}</VButton>
      </div>

      <Transition name="vdw-expand">
        <div v-if="advanced" id="llm-advanced-options">
          <div class="llm-defaults--dialog">
            <section v-for="group in advancedGroups" :key="group.key" class="llm-group">
              <header><h3>{{ group.title }}</h3></header>
              <div class="llm-defaults">
                <VField
                  v-for="key in group.keys"
                  :key="key"
                  :label="llmOption(key).label"
                  :hint="llmOption(key).unit
                    ? `${llmOption(key).min}–${llmOption(key).max} ${llmOption(key).unit}`
                    : `${llmOption(key).min}–${llmOption(key).max}`"
                >
                  <template #default="{ id }">
                    <el-input-number
                      :id="id"
                      v-model="form.advanced_options[key] as number"
                      :min="llmOption(key).min"
                      :max="llmOption(key).max"
                      :step="llmOption(key).step"
                      :precision="llmOption(key).precision"
                      :controls="false"
                    />
                  </template>
                </VField>
              </div>
            </section>
          </div>
        </div>
      </Transition>

      <template #footer>
        <VButton variant="quiet" @click="dialog = false">取消</VButton>
        <VButton variant="primary" :loading="saving" :disabled="!canSave" @click="save">
          保存
        </VButton>
      </template>
    </el-dialog>
  </main>
</template>

<style scoped>
.llm-tabs {
  display: grid;
  align-content: start;
  gap: 14px;
}

.llm-conn {
  font-size: 14px;
}

.llm-conn.is-ok { color: var(--vdw-ok); }
.llm-conn.is-danger { color: var(--vdw-danger); }
.llm-conn.is-idle { color: var(--vdw-ink-3); }

/* 行操作左对齐，与其它列同一起点（4.1）。原为 flex-end，操作列孤零零贴右边，
   与左对齐的表头对不上。 */
.row-actions {
  display: flex;
  gap: 2px;
}

.llm-defaults__lead {
  max-width: 800px;
  margin: 0 0 4px;
  color: var(--vdw-ink-2);
  font-size: 14px;
  line-height: 1.6;
}

.llm-group + .llm-group {
  margin-top: 22px;
  padding-top: 20px;
  border-top: 1px solid var(--vdw-line);
}

.llm-group > header {
  margin-bottom: 14px;
}

.llm-group h3 {
  font-size: 15px;
  font-weight: 600;
}

.llm-group > header p {
  margin: 4px 0 0;
  color: var(--vdw-ink-2);
  font-size: 14px;
}

.llm-defaults {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 18px;
}

/* 键名以等宽小字附在输入框下方：调 API 时需要，但不该抢中文名的位置 */
.llm-key {
  display: block;
  margin-top: 5px;
  color: var(--vdw-ink-3);
  font-size: 13px;
}

.llm-defaults :deep(.el-input-number) {
  width: 100%;
}

.llm-defaults__save {
  margin-left: auto;
}

.llm-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 18px;
}

.llm-form__wide {
  grid-column: 1 / -1;
}

.llm-form :deep(.el-select),
.llm-form :deep(.el-input) {
  width: 100%;
}

.llm-form__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--vdw-line);
}

.llm-defaults--dialog {
  margin-top: 16px;
}

.llm-defaults--dialog .llm-group + .llm-group {
  margin-top: 18px;
  padding-top: 16px;
}
</style>
