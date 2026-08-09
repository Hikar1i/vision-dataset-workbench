<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getAuthStatus, login } from '../api/auth'
import VButton from '../ui/VButton.vue'

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

          <VButton variant="secondary" type="submit"
            :loading="submitting"
            :disabled="!username || !password">
            登录工作台
          </VButton>
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
