<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import type { CreateFilesystemDirectory, LoadFilesystemEntries } from '../api/filesystem'
import { createSetupDirectory, initializeWorkspace, listSetupDirectories } from '../api/setup'
import ServerFilePicker from '../components/ServerFilePicker.vue'

const router = useRouter()
const step = ref(0)
const token = ref('')
const parent = ref('.')
const username = ref('admin')
const password = ref('')
const passwordConfirmation = ref('')
const submitting = ref(false)
const error = ref('')
const workspaceDisplay = computed(() => {
  const prefix = parent.value === '.' ? '~' : `~/${parent.value}`
  return `${prefix}/.vision-dataset-workbench`
})
const loadDirectories: LoadFilesystemEntries = (query) => listSetupDirectories(token.value, query)
const createDirectory: CreateFilesystemDirectory = (directory, name) =>
  createSetupDirectory(token.value, directory, name)

async function initialize() {
  submitting.value = true
  error.value = ''
  try {
    await initializeWorkspace(token.value, {
      parent: parent.value,
      username: username.value,
      password: password.value,
    })
    await router.replace('/login')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '初始化失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="setup-shell">
    <aside class="setup-context">
      <p class="eyebrow">VDW / FIRST RUN</p>
      <h1>建立受管工作区</h1>
      <p class="context-copy">把数据库、项目、模型和任务文件集中到一个可整体迁移的位置。</p>

      <ol class="steps" aria-label="初始化步骤">
        <li :class="{ active: step === 0, complete: step > 0 }">
          <span>01</span>
          验证终端口令
        </li>
        <li :class="{ active: step === 1 }">
          <span>02</span>
          创建工作区与管理员
        </li>
      </ol>

      <div class="path-preview">
        <span>WORKSPACE TARGET</span>
        <code>{{ workspaceDisplay }}</code>
      </div>
    </aside>

    <section class="setup-panel">
      <header>
        <span class="step-label">STEP {{ step + 1 }} / 2</span>
        <strong>{{ step === 0 ? '连接当前实例' : '配置首次启动' }}</strong>
      </header>

      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

      <section v-if="step === 0" class="form-section">
        <div>
          <h2>输入一次性初始化口令</h2>
          <p>口令只显示在服务端启动终端中，初始化完成后立即失效。</p>
        </div>
        <el-form label-position="top">
          <el-form-item label="初始化口令">
            <el-input
              v-model="token"
              data-test="token"
              type="password"
              show-password
              autocomplete="off"
              placeholder="粘贴终端中显示的口令"
            />
          </el-form-item>
        </el-form>
        <el-button
          data-test="continue"
          type="primary"
          :disabled="!token"
          @click="step = 1"
        >
          验证并选择目录
        </el-button>
      </section>

      <section v-else class="form-section wide">
        <div>
          <h2>选择工作区父目录</h2>
          <p>系统将在所选位置创建 <code>.vision-dataset-workbench</code>。</p>
        </div>
        <ServerFilePicker
          v-model="parent"
          mode="directory"
          allow-create-directory
          :load-entries="loadDirectories"
          :create-directory="createDirectory"
        />

        <div class="admin-heading">
          <h2>创建首个管理员</h2>
          <p>该账号负责后续用户审批与系统配置。</p>
        </div>
        <el-form label-position="top">
          <el-form-item label="用户名">
            <el-input v-model="username" data-test="username" autocomplete="username" />
          </el-form-item>
          <div class="password-grid">
            <el-form-item label="密码">
              <el-input
                v-model="password"
                data-test="password"
                type="password"
                show-password
                autocomplete="new-password"
              />
            </el-form-item>
            <el-form-item label="确认密码">
              <el-input
                v-model="passwordConfirmation"
                data-test="password-confirmation"
                type="password"
                show-password
                autocomplete="new-password"
              />
            </el-form-item>
          </div>
        </el-form>
        <footer class="actions">
          <el-button @click="step = 0">返回</el-button>
          <el-button
            data-test="initialize"
            type="primary"
            :loading="submitting"
            :disabled="
              username.length < 3 || password.length < 12 || password !== passwordConfirmation
            "
            @click="initialize"
          >
            创建工作区
          </el-button>
        </footer>
      </section>
    </section>
  </main>
</template>

<style scoped>
.setup-shell {
  --ink: #17212b;
  --muted: #687482;
  --line: #d8dee6;
  --signal: #2563eb;
  display: grid;
  grid-template-columns: minmax(260px, 32%) minmax(0, 1fr);
  min-height: 100vh;
  background: #f4f7fa;
}

.setup-context {
  display: flex;
  flex-direction: column;
  padding: clamp(35px, 6vw, 79px);
  color: #f6f9fc;
  background: var(--ink);
}

.eyebrow,
.step-label,
.path-preview span {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
  letter-spacing: 0.1em;
}

.eyebrow {
  margin: 0 0 62px;
  color: #76dfc2;
}

.setup-context h1 {
  max-width: 396px;
  margin: 0;
  font-size: clamp(40px, 5vw, 70px);
  line-height: 0.98;
  letter-spacing: -0.05em;
}

.context-copy {
  max-width: 462px;
  margin: 31px 0 53px;
  color: #b8c3ce;
  line-height: 1.7;
}

.steps {
  display: grid;
  gap: 9px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.steps li {
  display: flex;
  gap: 18px;
  align-items: center;
  padding: 13px 0;
  color: #7f8d9b;
  border-bottom: 1px solid #2d3945;
}

.steps li span {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
}

.steps li.active,
.steps li.complete {
  color: white;
}

.steps li.active span {
  color: #76dfc2;
}

.path-preview {
  display: grid;
  gap: 11px;
  margin-top: auto;
  padding-top: 53px;
}

.path-preview span {
  color: #7f8d9b;
}

.path-preview code {
  overflow-wrap: anywhere;
  color: #76dfc2;
}

.setup-panel {
  width: min(1012px, calc(100% - 53px));
  margin: auto;
  padding: clamp(35px, 6vw, 79px) 0;
}

.setup-panel > header {
  display: grid;
  gap: 9px;
  margin-bottom: 53px;
  padding-bottom: 22px;
  color: var(--ink);
  border-bottom: 1px solid var(--line);
}

.step-label {
  color: var(--signal);
}

.form-section {
  display: grid;
  gap: 26px;
  max-width: 616px;
}

.form-section.wide {
  max-width: none;
}

h2 {
  margin: 0 0 8px;
  color: var(--ink);
  font-size: 26px;
  letter-spacing: -0.02em;
}

.form-section p {
  margin: 0;
  color: var(--muted);
  line-height: 1.6;
}

.admin-heading {
  margin-top: 22px;
}

.password-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 13px;
  padding-top: 22px;
  border-top: 1px solid var(--line);
}

@media (max-width: 800px) {
  .setup-shell {
    grid-template-columns: 1fr;
  }

  .setup-context {
    min-height: auto;
    padding: 31px 26px;
  }

  .eyebrow,
  .context-copy,
  .steps {
    display: none;
  }

  .setup-context h1 {
    font-size: 37px;
  }

  .path-preview {
    padding-top: 26px;
  }

  .setup-panel {
    width: min(100% - 35px, 1012px);
    padding: 35px 0;
  }

  .password-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
