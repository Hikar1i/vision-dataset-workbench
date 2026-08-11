<script setup lang="ts">
import { Check, CircleCheck, CircleClose, Close } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'

import {
  listUsers,
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
import { userStatus } from '../ui/status'

const users = ref<ManagedUser[]>([])
const statusFilter = ref('')
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const loading = ref(false)
const changingId = ref('')
const error = ref('')

const COLUMNS = 'minmax(220px, 1fr) 120px minmax(180px, 0.6fr) 180px'

const FILTERS = [
  { key: '', label: '全部' },
  { key: 'pending', label: '待审批' },
  { key: 'active', label: '正常' },
  { key: 'disabled', label: '已禁用' },
  { key: 'rejected', label: '已拒绝' },
]

const stamp = (value: string) => value.slice(0, 16).replace('T', ' ')

const pendingCount = computed(
  () => users.value.filter((user) => user.status === 'pending').length,
)

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

onMounted(() => load())
</script>

<template>
  <main class="content-page">
    <PageHeader title="用户与注册审批" kind="users">
      <template #meta>
        <span data-test="page-stat">
          {{ total }} 位用户<template v-if="pendingCount"> · {{ pendingCount }} 个待审批</template>
        </span>
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
              :sub="user.is_system_admin ? '系统管理员' : ''"
            />
            <VTag :tone="userStatus(user.status).tone">{{ userStatus(user.status).label }}</VTag>
            <time :datetime="user.created_at">{{ stamp(user.created_at) }}</time>
            <div class="row-actions">
              <template v-if="user.status === 'pending'">
                <VButton
                  :data-test="`approve-${user.id}`"
                  variant="default"
                  size="sm"
                  :loading="changingId === user.id"
                  @click="change(user, 'approve')"
                ><template #icon><el-icon><Check /></el-icon></template>批准</VButton>
                <VButton
                  variant="quiet"
                  size="sm"
                  :disabled="changingId === user.id"
                  @click="change(user, 'reject')"
                ><template #icon><el-icon><Close /></el-icon></template>拒绝</VButton>
              </template>
              <VButton
                v-else-if="user.status === 'active'"
                :data-test="`disable-${user.id}`"
                variant="quiet"
                size="sm"
                :loading="changingId === user.id"
                @click="change(user, 'disable')"
              ><template #icon><el-icon><CircleClose /></el-icon></template>禁用</VButton>
              <VButton
                v-else
                variant="default"
                size="sm"
                :loading="changingId === user.id"
                @click="change(user, 'enable')"
              ><template #icon><el-icon><CircleCheck /></el-icon></template>启用</VButton>
            </div>
          </VRow>

          <template #empty>
            <VEmpty
              v-if="!loading && !users.length"
              :title="statusFilter ? '这个状态下没有账号' : '还没有其他账号'"
              note="新用户提交注册申请后会出现在待审批列表。"
            >
              <VButton v-if="statusFilter" variant="default" @click="selectFilter('')">
                查看全部账号
              </VButton>
            </VEmpty>
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
  </main>
</template>

<style scoped>
time {
  color: var(--vdw-ink-2);
  font-size: 14px;
}

/* 行操作左对齐，与其它列同一起点（4.1）。原为 flex-end，操作列孤零零贴右边，
   与左对齐的表头对不上。 */
.row-actions {
  display: flex;
  gap: 2px;
}

.el-pagination {
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
