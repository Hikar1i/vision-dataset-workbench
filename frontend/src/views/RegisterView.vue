<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getAuthStatus, register } from '../api/auth'
import VButton from '../ui/VButton.vue'

const router = useRouter()
const username = ref('')
const password = ref('')
const passwordConfirmation = ref('')
const submitting = ref(false)
const submittedUsername = ref('')
const error = ref('')
const valid = computed(
  () =>
    username.value.length >= 3 &&
    password.value.length >= 12 &&
    password.value === passwordConfirmation.value,
)

onMounted(async () => {
  try {
    const status = await getAuthStatus()
    if (!status.registration_enabled) await router.replace('/login')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取注册状态'
  }
})

async function submit() {
  if (!valid.value) return
  submitting.value = true
  error.value = ''
  try {
    const user = await register(username.value, password.value)
    submittedUsername.value = user.username
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '注册申请提交失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="utility-shell">
    <header class="utility-topbar">
      <span class="utility-brand">VISION DATASET WORKBENCH</span>
      <router-link to="/login">返回登录</router-link>
    </header>

    <section class="utility-card">
      <template v-if="submittedUsername">
        <span class="utility-code">REGISTRATION / PENDING</span>
        <h1>等待管理员审批</h1>
        <p>
          账号 <strong>{{ submittedUsername }}</strong> 已提交。管理员批准后即可登录当前实例。
        </p>
        <VButton variant="primary" @click="router.replace('/login')">返回登录</VButton>
      </template>

      <template v-else>
        <header class="utility-heading">
          <span class="utility-code">REGISTRATION / REQUEST</span>
          <h1>申请工作台账号</h1>
          <p>注册不会立即登录；申请需要系统管理员审批。</p>
        </header>

        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

        <form @submit.prevent="submit">
          <el-form label-position="top">
            <el-form-item label="用户名">
              <el-input
                v-model="username"
                data-test="username"
                autocomplete="username"
                placeholder="3–64 个字母、数字或 . _ -"
              />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="password"
                data-test="password"
                type="password"
                show-password
                autocomplete="new-password"
                placeholder="至少 12 个字符"
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
          </el-form>
          <VButton variant="secondary" type="submit"
            :loading="submitting"
            :disabled="!valid">
            提交注册申请
          </VButton>
        </form>
      </template>
    </section>
  </main>
</template>
