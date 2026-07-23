<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  listUsers,
  setUserStatus,
  type ManagedUser,
  type UserAction,
} from '../api/auth'

const users = ref<ManagedUser[]>([])
const statusFilter = ref('')
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const loading = ref(false)
const changingId = ref('')
const error = ref('')

const statusLabels: Record<ManagedUser['status'], string> = {
  pending: '待审批',
  active: '正常',
  rejected: '已拒绝',
  disabled: '已禁用',
}

async function load(nextPage = page.value) {
  loading.value = true
  error.value = ''
  try {
    const result = await listUsers(statusFilter.value, nextPage)
    users.value = result.items
    page.value = result.page
    pageSize.value = result.page_size
    total.value = result.total
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '用户列表加载失败'
  } finally {
    loading.value = false
  }
}

async function change(user: ManagedUser, action: UserAction) {
  changingId.value = user.id
  error.value = ''
  try {
    const updated = await setUserStatus(user.id, action)
    const index = users.value.findIndex((candidate) => candidate.id === updated.id)
    if (index !== -1) users.value[index] = updated
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '用户状态修改失败'
  } finally {
    changingId.value = ''
  }
}

onMounted(() => load())
</script>

<template>
  <main class="users-shell">
    <header class="users-header">
      <div>
        <span class="utility-code">ADMIN / USERS</span>
        <h1>用户与注册审批</h1>
        <p>审批新账号，或控制现有账号能否登录当前实例。</p>
      </div>
      <router-link to="/ready">返回工作台</router-link>
    </header>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <section class="users-panel">
      <div class="table-tools">
        <el-select
          v-model="statusFilter"
          aria-label="用户状态"
          placeholder="全部状态"
          @change="load(1)"
        >
          <el-option label="全部状态" value="" />
          <el-option label="待审批" value="pending" />
          <el-option label="正常" value="active" />
          <el-option label="已拒绝" value="rejected" />
          <el-option label="已禁用" value="disabled" />
        </el-select>
        <span>共 {{ total }} 个账号</span>
      </div>

      <el-table v-loading="loading" :data="users" row-key="id">
        <el-table-column label="用户名" min-width="190">
          <template #default="{ row }: { row: ManagedUser }">
            <strong>{{ row.username }}</strong>
            <span v-if="row.is_system_admin" class="admin-mark">系统管理员</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }: { row: ManagedUser }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" effect="plain">
              {{ statusLabels[row.status] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="190" />
        <el-table-column label="操作" min-width="220" align="right">
          <template #default="{ row }: { row: ManagedUser }">
            <template v-if="row.status === 'pending'">
              <el-button
                :data-test="`approve-${row.id}`"
                text
                type="primary"
                :loading="changingId === row.id"
                @click="change(row, 'approve')"
              >
                批准
              </el-button>
              <el-button text :disabled="changingId === row.id" @click="change(row, 'reject')">
                拒绝
              </el-button>
            </template>
            <el-button
              v-else-if="row.status === 'active'"
              :data-test="`disable-${row.id}`"
              text
              type="danger"
              :loading="changingId === row.id"
              @click="change(row, 'disable')"
            >
              禁用
            </el-button>
            <el-button
              v-else
              text
              type="primary"
              :loading="changingId === row.id"
              @click="change(row, 'enable')"
            >
              启用
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="total > pageSize"
        layout="prev, pager, next"
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        @current-change="load"
      />
    </section>
  </main>
</template>

<style scoped>
.users-shell {
  min-height: 100vh;
  padding: 32px clamp(20px, 4vw, 56px) 64px;
  color: #17212b;
  background: #f4f7fa;
}

.users-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
  padding-bottom: 24px;
  border-bottom: 1px solid #d8dee6;
}

.users-header h1 {
  margin: 12px 0 6px;
  font-size: 30px;
  letter-spacing: -0.035em;
}

.users-header p,
.table-tools {
  color: #687482;
}

.users-header p {
  margin: 0;
}

.users-header a {
  color: #2563eb;
  font-size: 14px;
  text-decoration: none;
}

.users-panel {
  margin-top: 20px;
  padding: 24px;
  background: white;
  border: 1px solid #d8dee6;
}

.table-tools {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  font-size: 13px;
}

.table-tools .el-select {
  width: 180px;
}

.admin-mark {
  margin-left: 10px;
  color: #687482;
  font-size: 12px;
  font-weight: 400;
}

.el-pagination {
  justify-content: flex-end;
  margin-top: 20px;
}

@media (max-width: 680px) {
  .users-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .users-panel {
    padding: 12px;
    overflow-x: auto;
  }
}
</style>
