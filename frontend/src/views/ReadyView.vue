<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getCurrentUser, logout, type CurrentUser } from '../api/auth'

const router = useRouter()
const user = ref<CurrentUser | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    user.value = await getCurrentUser()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取账号信息'
  }
})

async function signOut() {
  try {
    await logout()
    await router.replace('/login')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '退出失败'
  }
}
</script>

<template>
  <main class="workbench-shell">
    <header>
      <div>
        <span class="utility-code">VDW / WORKSPACE</span>
        <h1>Vision Dataset Workbench</h1>
      </div>
      <nav v-if="user" aria-label="账号操作">
        <span>{{ user.username }}</span>
        <router-link data-test="account-link" to="/account">账号设置</router-link>
        <router-link v-if="user.is_system_admin" data-test="users-link" to="/admin/users">
          用户管理
        </router-link>
        <el-button data-test="logout" text @click="signOut">退出</el-button>
      </nav>
    </header>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <section class="empty-workspace">
      <span>WORKSPACE / ONLINE</span>
      <h2>工作区已就绪</h2>
      <p>认证与用户管理已启用。数据集项目功能将在后续迭代接入此处。</p>
    </section>
  </main>
</template>

<style scoped>
.workbench-shell {
  min-height: 100vh;
  padding: 28px clamp(20px, 4vw, 56px);
  color: #17212b;
  background: #f4f7fa;
}

.workbench-shell > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 24px;
  border-bottom: 1px solid #d8dee6;
}

h1 {
  margin: 8px 0 0;
  font-size: 24px;
  letter-spacing: -0.025em;
}

nav {
  display: flex;
  align-items: center;
  gap: 18px;
  font-size: 14px;
}

nav > span {
  color: #687482;
}

nav a {
  color: #2563eb;
  text-decoration: none;
}

.empty-workspace {
  max-width: 720px;
  margin-top: 72px;
  padding: 36px;
  background: white;
  border: 1px solid #d8dee6;
}

.empty-workspace > span {
  color: #16866f;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
  letter-spacing: 0.1em;
}

.empty-workspace h2 {
  margin: 18px 0 8px;
  font-size: 28px;
}

.empty-workspace p {
  margin: 0;
  color: #687482;
  line-height: 1.65;
}

@media (max-width: 720px) {
  .workbench-shell > header,
  nav {
    align-items: flex-start;
  }

  .workbench-shell > header {
    flex-direction: column;
  }

  nav {
    flex-wrap: wrap;
  }
}
</style>
