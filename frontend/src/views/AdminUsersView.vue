<script setup lang="ts">
import { CircleCheck, CircleClose, CopyDocument, Plus, RefreshRight, User } from '@element-plus/icons-vue'
import { notify } from '../ui/notify'
import { onBeforeUnmount, onMounted, ref } from 'vue'

import {
  createUser,
  listUsers,
  resetUserPassword,
  setUserStatus,
  type ManagedUser,
  type UserAction,
} from '../api/auth'
import PageHeader from '../components/PageHeader.vue'
import VButton from '../ui/VButton.vue'
import VCellName from '../ui/VCellName.vue'
import VEmpty from '../ui/VEmpty.vue'
import VPanel from '../ui/VPanel.vue'
import VRow from '../ui/VRow.vue'
import VTable from '../ui/VTable.vue'
import VTag from '../ui/VTag.vue'
import { copyText } from '../ui/clipboard'
import { userStatus } from '../ui/status'

const users = ref<ManagedUser[]>([])
const statusFilter = ref('')
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const loading = ref(false)
const changingId = ref('')
const error = ref('')
const createOpen = ref(false)
const username = ref('')
const revealedPassword = ref('')
const revealedUsername = ref('')
const copied = ref(false)
let copyResetTimer: number | undefined

const COLUMNS = 'minmax(220px, 1fr) 120px minmax(180px, 0.6fr) 240px'
const FILTERS = [
  { key: '', label: '全部' },
  { key: 'active', label: '正常' },
  { key: 'disabled', label: '已禁用' },
]
const stamp = (value: string) => value.slice(0, 16).replace('T', ' ')

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

async function selectFilter(key: string) {
  statusFilter.value = key
  await load(1)
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

async function createAccount() {
  if (!username.value.trim()) return
  loading.value = true
  error.value = ''
  try {
    const created = await createUser(username.value.trim())
    revealedUsername.value = created.username
    revealedPassword.value = created.initial_password
    resetCopiedState()
    createOpen.value = false
    username.value = ''
    await load(1)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '账号创建失败'
  } finally {
    loading.value = false
  }
}

async function resetPassword(user: ManagedUser) {
  changingId.value = user.id
  error.value = ''
  try {
    const reset = await resetUserPassword(user.id)
    revealedUsername.value = reset.username
    revealedPassword.value = reset.initial_password
    resetCopiedState()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '密码重置失败'
  } finally {
    changingId.value = ''
  }
}

async function copyPassword() {
  try {
    await copyText(revealedPassword.value)
    copied.value = true
    notify.success('初始密码已复制。')
    if (copyResetTimer !== undefined) window.clearTimeout(copyResetTimer)
    copyResetTimer = window.setTimeout(resetCopiedState, 1500)
  } catch {
    resetCopiedState()
    notify.error('复制失败，请手动选择密码复制。')
  }
}

function resetCopiedState() {
  copied.value = false
  if (copyResetTimer !== undefined) {
    window.clearTimeout(copyResetTimer)
    copyResetTimer = undefined
  }
}

function closePasswordDialog() {
  revealedPassword.value = ''
  resetCopiedState()
}

onMounted(() => load())
onBeforeUnmount(resetCopiedState)
</script>

<template>
  <main class="content-page">
    <PageHeader title="用户管理" kind="users" :icon="User">
      <template #meta><span data-test="page-stat">{{ total }} 位用户</span></template>
      <template #actions>
        <VButton variant="primary" data-test="create-user" @click="createOpen = true">
          <template #icon><el-icon><Plus /></el-icon></template>创建账号
        </VButton>
      </template>
      <template #tabs>
        <button
          v-for="option in FILTERS"
          :key="option.key || 'all'"
          type="button"
          :class="{ 'is-active': statusFilter === option.key }"
          :aria-selected="statusFilter === option.key"
          @click="selectFilter(option.key)"
        >{{ option.label }}</button>
      </template>
    </PageHeader>

    <div class="content-body">
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <VPanel v-loading="loading" flush>
        <VTable :columns="COLUMNS" :headers="['用户名', '状态', '创建时间', '操作']">
          <VRow v-for="user in users" :key="user.id" :columns="COLUMNS">
            <VCellName
              :name="user.username"
              :sub="user.is_system_admin ? '系统管理员' : user.must_change_password ? '等待首次改密' : ''"
            />
            <VTag :tone="userStatus(user.status).tone">{{ userStatus(user.status).label }}</VTag>
            <time :datetime="user.created_at">{{ stamp(user.created_at) }}</time>
            <div v-if="!user.is_system_admin" class="row-actions">
              <VButton
                v-if="user.status === 'active'"
                :data-test="`disable-${user.id}`"
                variant="quiet"
                size="sm"
                :loading="changingId === user.id"
                @click="change(user, 'disable')"
              ><template #icon><el-icon><CircleClose /></el-icon></template>禁用</VButton>
              <VButton
                v-else
                :data-test="`enable-${user.id}`"
                variant="default"
                size="sm"
                :loading="changingId === user.id"
                @click="change(user, 'enable')"
              ><template #icon><el-icon><CircleCheck /></el-icon></template>启用</VButton>
              <VButton
                :data-test="`reset-${user.id}`"
                variant="quiet"
                size="sm"
                :loading="changingId === user.id"
                @click="resetPassword(user)"
              ><template #icon><el-icon><RefreshRight /></el-icon></template>重新生成密码</VButton>
            </div>
          </VRow>
          <template #empty>
            <VEmpty v-if="!loading && !users.length" title="暂无账号" note="由系统管理员创建普通账号。" />
          </template>
        </VTable>
      </VPanel>
      <el-pagination
        v-if="total > pageSize"
        layout="prev, pager, next"
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        @current-change="load"
      />
    </div>

    <el-dialog v-model="createOpen" title="创建普通账号" width="460px">
      <el-form label-position="top" @submit.prevent="createAccount">
        <el-form-item label="用户名">
          <el-input v-model="username" data-test="new-username" autocomplete="off" />
        </el-form-item>
      </el-form>
      <template #footer>
        <VButton variant="quiet" @click="createOpen = false">取消</VButton>
        <VButton data-test="submit-user" variant="primary" :disabled="!username.trim()" @click="createAccount">创建</VButton>
      </template>
    </el-dialog>

    <el-dialog
      :model-value="Boolean(revealedPassword)"
      title="一次性初始密码"
      width="520px"
      @close="closePasswordDialog"
    >
      <el-alert title="关闭后系统不会再显示此密码；遗失时请重新生成。" type="warning" :closable="false" />
      <p>{{ revealedUsername }}</p>
      <el-input data-test="initial-password" :model-value="revealedPassword" readonly>
        <template #append>
          <el-button
            class="copy-password-button"
            data-test="copy-initial-password"
            :title="copied ? '已复制' : '复制初始密码'"
            :aria-label="copied ? '已复制' : '复制初始密码'"
            @click="copyPassword"
          >
            <el-icon><CircleCheck v-if="copied" /><CopyDocument v-else /></el-icon>
          </el-button>
        </template>
      </el-input>
    </el-dialog>
  </main>
</template>

<style scoped>
time { color: var(--vdw-ink-2); font-size: 14px; }
.row-actions { display: flex; gap: 4px; flex-wrap: wrap; }
.el-pagination { justify-content: flex-end; margin-top: 14px; }
.copy-password-button { transition: color 150ms ease, background-color 150ms ease; }
.copy-password-button:hover,
.copy-password-button:focus-visible { color: var(--vdw-accent-ink); background: var(--vdw-accent-soft); }
</style>
