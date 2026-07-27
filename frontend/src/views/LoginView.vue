<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getAuthStatus, login } from '../api/auth'

const router = useRouter()
const username = ref('')
const password = ref('')
const registrationEnabled = ref(false)
const mode = ref<'multi' | 'single'>('multi')
const submitting = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    const status = await getAuthStatus()
    registrationEnabled.value = status.registration_enabled
    mode.value = status.mode
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取实例状态'
  }
})

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await login(username.value, password.value)
    await router.replace('/projects')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '登录失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="access-shell">
    <aside class="instance-panel">
      <div class="instance-heading">
        <p class="eyebrow">VDW / ACCESS</p>
        <span class="mode-chip">{{ mode === 'multi' ? 'MULTI USER' : 'SINGLE USER' }}</span>
      </div>

      <div class="vision-frame" aria-hidden="true">
        <span class="frame-label">WORKSPACE / READY</span>
        <div class="target-box"><i /></div>
      </div>

      <div class="instance-copy">
        <h1>Vision Dataset<br />Workbench</h1>
        <p>集中管理数据集、采样任务与后续模型工作流。</p>
      </div>

      <dl class="instance-readout">
        <div><dt>SESSION</dt><dd>SERVER-SIDE</dd></div>
        <div><dt>ACCESS</dt><dd>INTERNAL</dd></div>
      </dl>
    </aside>

    <section class="login-panel">
      <div class="login-box">
        <header>
          <span class="section-code">AUTH / 01</span>
          <h2>进入数据工作台</h2>
          <p>使用当前实例中的账号继续。</p>
        </header>

        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

        <form @submit.prevent="submit">
          <el-form label-position="top">
            <el-form-item label="用户名">
              <el-input
                v-model="username"
                data-test="username"
                autocomplete="username"
                autofocus
                placeholder="输入用户名"
              />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="password"
                data-test="password"
                type="password"
                show-password
                autocomplete="current-password"
                placeholder="输入密码"
              />
            </el-form-item>
          </el-form>

          <el-button
            native-type="submit"
            type="primary"
            :loading="submitting"
            :disabled="!username || !password"
          >
            登录工作台
          </el-button>
        </form>

        <footer>
          <template v-if="registrationEnabled">
            <span>还没有账号？</span>
            <router-link data-test="register-link" to="/register">提交注册申请</router-link>
          </template>
          <span v-else>账号由系统管理员管理</span>
        </footer>
      </div>
    </section>
  </main>
</template>

<style scoped>
.access-shell {
  --ink: #17212b;
  --muted: #687482;
  --line: #d8dee6;
  --signal: #2563eb;
  --mint: #76dfc2;
  display: grid;
  grid-template-columns: minmax(340px, 42%) minmax(0, 1fr);
  min-height: 100vh;
  background: #f4f7fa;
}

.instance-panel {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  padding: clamp(35px, 5vw, 70px);
  overflow: hidden;
  color: #f6f9fc;
  background: var(--ink);
}

.instance-heading,
.instance-readout,
.instance-readout div {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.eyebrow,
.mode-chip,
.frame-label,
.section-code,
.instance-readout {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  letter-spacing: 0.11em;
}

.eyebrow {
  margin: 0;
  color: var(--mint);
}

.mode-chip {
  padding: 7px 9px;
  color: #b8c3ce;
  border: 1px solid #3a4652;
}

.vision-frame {
  position: relative;
  width: min(100%, 506px);
  aspect-ratio: 1.55;
  margin: clamp(56px, 10vh, 112px) 0 44px;
  border: 1px solid #3a4652;
  background:
    linear-gradient(#26323e 1px, transparent 1px),
    linear-gradient(90deg, #26323e 1px, transparent 1px);
  background-size: 25% 25%;
}

.vision-frame::before,
.vision-frame::after {
  position: absolute;
  width: 35px;
  height: 35px;
  content: '';
}

.vision-frame::before {
  top: -1px;
  left: -1px;
  border-top: 2px solid var(--mint);
  border-left: 2px solid var(--mint);
}

.vision-frame::after {
  right: -1px;
  bottom: -1px;
  border-right: 2px solid var(--mint);
  border-bottom: 2px solid var(--mint);
}

.frame-label {
  position: absolute;
  top: 12px;
  left: 14px;
  color: #8795a3;
}

.target-box {
  position: absolute;
  top: 30%;
  left: 24%;
  width: 48%;
  height: 42%;
  border: 1px solid var(--mint);
}

.target-box i,
.target-box i::after {
  position: absolute;
  top: 50%;
  left: 50%;
  display: block;
  width: 29px;
  height: 1px;
  content: '';
  background: var(--mint);
  transform: translate(-50%, -50%);
}

.target-box i::after {
  transform: translate(-50%, -50%) rotate(90deg);
}

.instance-copy h1 {
  margin: 0;
  font-family: Bahnschrift, "Arial Narrow", "Noto Sans SC", sans-serif;
  font-size: clamp(40px, 4vw, 64px);
  font-stretch: condensed;
  font-weight: 600;
  line-height: 0.98;
  letter-spacing: -0.04em;
}

.instance-copy p {
  max-width: 473px;
  margin: 26px 0 0;
  color: #aab6c2;
  line-height: 1.7;
}

.instance-readout {
  gap: 31px;
  margin: auto 0 0;
  padding-top: 53px;
  color: #7f8d9b;
  border-top: 1px solid #2d3945;
}

.instance-readout div {
  flex: 1;
}

.instance-readout dd {
  margin: 0;
  color: var(--mint);
}

.login-panel {
  display: grid;
  min-height: 100vh;
  padding: 35px;
  place-items: center;
}

.login-box {
  display: grid;
  gap: 31px;
  width: min(484px, 100%);
}

.login-box header {
  padding-bottom: 26px;
  border-bottom: 1px solid var(--line);
}

.section-code {
  color: var(--signal);
}

.login-box h2 {
  margin: 15px 0 9px;
  color: var(--ink);
  font-size: 33px;
  letter-spacing: -0.035em;
}

.login-box header p,
.login-box footer {
  margin: 0;
  color: var(--muted);
  font-size: 15px;
}

form,
form :deep(.el-form) {
  display: grid;
}

form {
  gap: 9px;
}

form :deep(.el-form-item) {
  margin-bottom: 24px;
}

form > .el-button {
  width: 100%;
  min-height: 46px;
}

.login-box footer {
  display: flex;
  gap: 9px;
  min-height: 26px;
  padding-top: 22px;
  border-top: 1px solid var(--line);
}

.login-box footer a {
  color: var(--signal);
  font-weight: 600;
  text-decoration: none;
}

.login-box footer a:hover {
  text-decoration: underline;
}

@media (max-width: 820px) {
  .access-shell {
    grid-template-columns: 1fr;
  }

  .instance-panel {
    min-height: auto;
    padding: 26px;
  }

  .vision-frame,
  .instance-copy p,
  .instance-readout {
    display: none;
  }

  .instance-copy h1 {
    margin-top: 31px;
    font-size: 33px;
    line-height: 1.05;
  }

  .login-panel {
    min-height: auto;
    padding: 44px 22px;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
