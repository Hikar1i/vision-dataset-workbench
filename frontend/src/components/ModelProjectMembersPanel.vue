<script setup lang="ts">
import { notify } from '../ui/notify'
import { computed, ref, watch } from 'vue'

import { can } from '../api/access'
import {
  addModelProjectMember,
  changeModelProjectMemberRole,
  listModelProjectMembers,
  removeModelProjectMember,
  type ModelProject,
  type ModelProjectMember,
} from '../api/models'
import VButton from '../ui/VButton.vue'
import VPanel from '../ui/VPanel.vue'
import VTag from '../ui/VTag.vue'
import { userStatus } from '../ui/status'

const props = defineProps<{
  project: ModelProject
  scopeDescription: string
}>()

const members = ref<ModelProjectMember[]>([])
const memberUsername = ref('')
const memberRole = ref<'editor' | 'viewer'>('viewer')
const changingMember = ref('')
let loadVersion = 0

const canManage = computed(
  () => !props.project.system_key && can(props.project.access, 'project.members.manage'),
)

async function loadMembers() {
  const version = ++loadVersion
  if (props.project.system_key) {
    members.value = []
    return
  }
  try {
    const next = await listModelProjectMembers(props.project.id)
    if (version === loadVersion) members.value = next
  } catch (reason) {
    if (version === loadVersion) {
      notify.error(reason instanceof Error ? reason.message : '项目成员加载失败')
    }
  }
}

async function addMember() {
  if (!memberUsername.value.trim()) return
  changingMember.value = 'new'
  try {
    members.value.push(await addModelProjectMember(
      props.project.id,
      memberUsername.value.trim(),
      memberRole.value,
    ))
    memberUsername.value = ''
  } catch (reason) {
    notify.error(reason instanceof Error ? reason.message : '成员添加失败')
  } finally {
    changingMember.value = ''
  }
}

async function toggleRole(member: ModelProjectMember) {
  changingMember.value = member.id
  try {
    const changed = await changeModelProjectMemberRole(
      props.project.id,
      member.id,
      member.role === 'editor' ? 'viewer' : 'editor',
    )
    const index = members.value.findIndex((item) => item.id === member.id)
    if (index !== -1) members.value[index] = changed
  } catch (reason) {
    notify.error(reason instanceof Error ? reason.message : '成员角色修改失败')
  } finally {
    changingMember.value = ''
  }
}

async function removeMember(member: ModelProjectMember) {
  changingMember.value = member.id
  try {
    await removeModelProjectMember(props.project.id, member.id)
    members.value = members.value.filter((item) => item.id !== member.id)
  } catch (reason) {
    notify.error(reason instanceof Error ? reason.message : '成员移除失败')
  } finally {
    changingMember.value = ''
  }
}

watch(() => props.project.id, loadMembers, { immediate: true })
</script>

<template>
  <VPanel title="项目成员与权限" data-test="model-project-members-panel">
    <p class="scope-description">{{ scopeDescription }}</p>
    <el-alert
      v-if="project.system_key"
      title="这是系统内置项目，所有正常账号自动获得只读访问，不接受显式成员授权。"
      type="info"
      :closable="false"
      show-icon
    />
    <template v-else>
      <form v-if="canManage" class="member-form" @submit.prevent="addMember">
        <el-input
          v-model="memberUsername"
          data-test="model-member-username"
          placeholder="现有用户名"
        />
        <el-select v-model="memberRole" aria-label="成员角色">
          <el-option label="只读" value="viewer" />
          <el-option label="编辑者" value="editor" />
        </el-select>
        <VButton
          type="submit"
          data-test="add-model-member"
          :loading="changingMember === 'new'"
          :disabled="!memberUsername.trim()"
        >添加成员</VButton>
      </form>
      <div class="member-list">
        <article v-for="member in members" :key="member.id" class="member-row">
          <strong>{{ member.username }}</strong>
          <VTag :tone="userStatus(member.status).tone">{{ userStatus(member.status).label }}</VTag>
          <VTag :tone="member.role === 'owner' ? 'run' : 'idle'">
            {{ member.role === 'owner' ? '所有者' : member.role === 'editor' ? '编辑者' : '只读' }}
          </VTag>
          <div v-if="canManage && member.role !== 'owner'" class="member-actions">
            <VButton
              size="sm"
              variant="quiet"
              :data-test="`toggle-model-member-${member.id}`"
              :loading="changingMember === member.id"
              @click="toggleRole(member)"
            >{{ member.role === 'editor' ? '改为只读' : '改为编辑者' }}</VButton>
            <VButton
              size="sm"
              variant="quiet"
              :data-test="`remove-model-member-${member.id}`"
              :disabled="changingMember === member.id"
              @click="removeMember(member)"
            >移除</VButton>
          </div>
        </article>
        <p v-if="!members.length" class="cell-muted">暂无项目成员。</p>
      </div>
    </template>
  </VPanel>
</template>

<style scoped>
.scope-description { margin: 0 0 14px; color: var(--vdw-ink-2); font-size: 14px; }
.member-form { display: grid; grid-template-columns: minmax(180px, 1fr) 130px auto; gap: 8px; margin-bottom: 14px; }
.member-list { display: grid; gap: 8px; }
.member-row { display: grid; grid-template-columns: minmax(160px, 1fr) auto auto minmax(0, 1fr); align-items: center; gap: 10px; padding: 10px 0; border-top: 1px solid var(--vdw-line); }
.member-actions { display: flex; justify-content: flex-end; gap: 4px; }
</style>
