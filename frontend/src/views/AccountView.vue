<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { changePassword } from '../api/auth'

const router = useRouter()
const currentPassword = ref('')
const newPassword = ref('')
const passwordConfirmation = ref('')
const submitting = ref(false)
const error = ref('')
const valid = computed(
  () =>
    currentPassword.value.length > 0 &&
    newPassword.value.length >= 12 &&
    newPassword.value === passwordConfirmation.value,
)

async function submit() {
  if (!valid.value) return
  submitting.value = true
  error.value = ''
  try {
    await changePassword(currentPassword.value, newPassword.value)
    await router.replace('/ready')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '密码修改失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="utility-shell">
    <header class="utility-topbar">
      <span class="utility-brand">VDW</span>
      <router-link to="/ready">返回工作台</router-link>
    </header>

    <section class="utility-card">
      <header class="utility-heading">
        <span class="utility-code">ACCOUNT / PASSWORD</span>
        <h1>修改登录密码</h1>
        <p>保存后，当前账号在其他浏览器中的会话会立即失效。</p>
      </header>

      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

      <form @submit.prevent="submit">
        <el-form label-position="top">
          <el-form-item label="当前密码">
            <el-input
              v-model="currentPassword"
              data-test="current-password"
              type="password"
              show-password
              autocomplete="current-password"
            />
          </el-form-item>
          <el-form-item label="新密码">
            <el-input
              v-model="newPassword"
              data-test="new-password"
              type="password"
              show-password
              autocomplete="new-password"
              placeholder="至少 12 个字符"
            />
          </el-form-item>
          <el-form-item label="确认新密码">
            <el-input
              v-model="passwordConfirmation"
              data-test="password-confirmation"
              type="password"
              show-password
              autocomplete="new-password"
            />
          </el-form-item>
        </el-form>
        <el-button
          data-test="save-password"
          native-type="submit"
          type="primary"
          :loading="submitting"
          :disabled="!valid"
        >
          保存新密码
        </el-button>
      </form>
    </section>
  </main>
</template>
