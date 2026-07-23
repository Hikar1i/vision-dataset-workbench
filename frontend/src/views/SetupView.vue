<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { initializeWorkspace } from '../api/setup'
import ServerDirectoryPicker from '../components/ServerDirectoryPicker.vue'

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

async function initialize() {
  submitting.value = true
  error.value = ''
  try {
    await initializeWorkspace(token.value, {
      parent: parent.value,
      username: username.value,
      password: password.value,
    })
    await router.replace('/ready')
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
        <ServerDirectoryPicker v-model="parent" :token="token" />

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
  padding: clamp(32px, 6vw, 72px);
  color: #f6f9fc;
  background: var(--ink);
}

.eyebrow,
.step-label,
.path-preview span {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  letter-spacing: 0.1em;
}

.eyebrow {
  margin: 0 0 56px;
  color: #76dfc2;
}

.setup-context h1 {
  max-width: 360px;
  margin: 0;
  font-size: clamp(36px, 5vw, 64px);
  line-height: 0.98;
  letter-spacing: -0.05em;
}

.context-copy {
  max-width: 420px;
  margin: 28px 0 48px;
  color: #b8c3ce;
  line-height: 1.7;
}

.steps {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.steps li {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 12px 0;
  color: #7f8d9b;
  border-bottom: 1px solid #2d3945;
}

.steps li span {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
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
  gap: 10px;
  margin-top: auto;
  padding-top: 48px;
}

.path-preview span {
  color: #7f8d9b;
}

.path-preview code {
  overflow-wrap: anywhere;
  color: #76dfc2;
}

.setup-panel {
  width: min(920px, calc(100% - 48px));
  margin: auto;
  padding: clamp(32px, 6vw, 72px) 0;
}

.setup-panel > header {
  display: grid;
  gap: 8px;
  margin-bottom: 48px;
  padding-bottom: 20px;
  color: var(--ink);
  border-bottom: 1px solid var(--line);
}

.step-label {
  color: var(--signal);
}

.form-section {
  display: grid;
  gap: 24px;
  max-width: 560px;
}

.form-section.wide {
  max-width: none;
}

h2 {
  margin: 0 0 8px;
  color: var(--ink);
  font-size: 24px;
  letter-spacing: -0.02em;
}

.form-section p {
  margin: 0;
  color: var(--muted);
  line-height: 1.6;
}

.admin-heading {
  margin-top: 20px;
}

.password-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
}

@media (max-width: 800px) {
  .setup-shell {
    grid-template-columns: 1fr;
  }

  .setup-context {
    min-height: auto;
    padding: 28px 24px;
  }

  .eyebrow,
  .context-copy,
  .steps {
    display: none;
  }

  .setup-context h1 {
    font-size: 34px;
  }

  .path-preview {
    padding-top: 24px;
  }

  .setup-panel {
    width: min(100% - 32px, 920px);
    padding: 32px 0;
  }

  .password-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
