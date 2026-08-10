<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { ApiError } from '../api/auth'
import { useProjectHeaderHost } from '../ui/projectHeaderHost'
import VButton from '../ui/VButton.vue'
import VField from '../ui/VField.vue'
import VPanel from '../ui/VPanel.vue'
import VTag from '../ui/VTag.vue'
import { userStatus } from '../ui/status'
import {
  addMember,
  changeMemberRole,
  getProject,
  listMembers,
  removeMember,
  updateProject,
  type Project,
  type ProjectMember,
} from '../api/projects'

const props = defineProps<{ project: Project }>()
const emit = defineEmits<{ 'project-updated': [project: Project] }>()
const projectId = props.project.id
const project = computed(() => props.project)
const members = ref<ProjectMember[]>([])
const name = ref('')
const description = ref('')
const memberUsername = ref('')
const memberRole = ref<'editor' | 'viewer'>('viewer')
const loading = ref(false)
const saving = ref(false)
const changingMember = ref('')
const error = ref('')

const canEdit = computed(() => project.value?.role === 'owner' || project.value?.role === 'editor')
const canManageMembers = computed(() => project.value?.role === 'owner')
const roleLabels = { owner: '所有者', editor: '编辑者', viewer: '只读' } as const

function setProject(value: Project) {
  name.value = value.name
  description.value = value.description
  emit('project-updated', value)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    members.value = await listMembers(projectId)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '项目加载失败'
  } finally {
    loading.value = false
  }
}

async function saveProject() {
  if (!project.value || !canEdit.value || !name.value.trim()) return
  saving.value = true
  error.value = ''
  try {
    setProject(
      await updateProject(
        projectId,
        name.value,
        description.value,
        project.value.version,
      ),
    )
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '项目信息保存失败'
    if (reason instanceof ApiError && reason.status === 409) {
      setProject(await getProject(projectId))
    }
  } finally {
    saving.value = false
  }
}

async function addProjectMember() {
  if (!memberUsername.value.trim()) return
  changingMember.value = 'new'
  error.value = ''
  try {
    members.value.push(
      await addMember(projectId, memberUsername.value, memberRole.value),
    )
    memberUsername.value = ''
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '成员添加失败'
  } finally {
    changingMember.value = ''
  }
}

async function toggleRole(member: ProjectMember) {
  const role = member.role === 'editor' ? 'viewer' : 'editor'
  changingMember.value = member.id
  error.value = ''
  try {
    const changed = await changeMemberRole(projectId, member.id, role)
    const index = members.value.findIndex((candidate) => candidate.id === member.id)
    if (index !== -1) members.value[index] = changed
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '成员角色修改失败'
  } finally {
    changingMember.value = ''
  }
}

async function remove(member: ProjectMember) {
  changingMember.value = member.id
  error.value = ''
  try {
    await removeMember(projectId, member.id)
    members.value = members.value.filter((candidate) => candidate.id !== member.id)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '成员移除失败'
  } finally {
    changingMember.value = ''
  }
}

onMounted(() => {
  name.value = project.value.name
  description.value = project.value.description
  void load()
})

const headerHost = useProjectHeaderHost()
</script>

<template>
  <main class="content-body settings-body">
    <Teleport defer :disabled="!headerHost" to="#project-page-meta">
      <span data-test="page-stat">{{ members.length }} 位成员</span>
    </Teleport>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <div v-loading="loading" class="settings-grid">
      <VPanel v-if="project" title="项目信息">
        <div v-if="canEdit" class="settings-form">
          <VField label="项目名称" required>
            <template #default="{ id }">
              <el-input :id="id" v-model="name" data-test="project-name" maxlength="128" />
            </template>
          </VField>
          <VField label="描述">
            <template #default="{ id }">
              <el-input
                :id="id"
                v-model="description"
                data-test="project-description"
                type="textarea"
                :rows="4"
                maxlength="2000"
              />
            </template>
          </VField>
        </div>

        <dl v-else class="readonly-metadata">
          <div><dt>名称</dt><dd>{{ project.name }}</dd></div>
          <div><dt>描述</dt><dd>{{ project.description || '暂无描述' }}</dd></div>
        </dl>

        <template v-if="canEdit" #footer>
          <VButton
            variant="primary"
            data-test="save-project"
            class="settings-save"
            :loading="saving"
            :disabled="!name.trim()"
            @click="saveProject"
          >保存项目信息</VButton>
        </template>
      </VPanel>

      <VPanel v-if="project" title="项目成员">
        <template #head>
          <span class="member-count">{{ members.length }} 人</span>
        </template>

        <form v-if="canManageMembers" class="member-form" @submit.prevent="addProjectMember">
          <el-input
            v-model="memberUsername"
            data-test="member-username"
            placeholder="现有用户名"
          />
          <el-select v-model="memberRole" aria-label="成员角色">
            <el-option label="只读" value="viewer" />
            <el-option label="编辑者" value="editor" />
          </el-select>
          <VButton
            data-test="add-member"
            type="submit"
            :loading="changingMember === 'new'"
            :disabled="!memberUsername.trim()"
          >添加成员</VButton>
        </form>

        <div class="member-list">
          <article v-for="member in members" :key="member.id" class="member-row">
            <div class="member-identity">
              <strong>{{ member.username }}</strong>
              <VTag :tone="userStatus(member.status).tone">
                {{ userStatus(member.status).label }}
              </VTag>
            </div>
            <VTag :tone="member.role === 'owner' ? 'run' : 'idle'">
              {{ roleLabels[member.role] }}
            </VTag>
            <div v-if="canManageMembers && member.role !== 'owner'" class="member-actions">
              <VButton
                variant="quiet"
                size="sm"
                :loading="changingMember === member.id"
                @click="toggleRole(member)"
              >{{ member.role === 'editor' ? '改为只读' : '改为编辑者' }}</VButton>
              <VButton
                variant="quiet"
                size="sm"
                :data-test="`remove-${member.id}`"
                :disabled="changingMember === member.id"
                @click="remove(member)"
              >移除</VButton>
            </div>
          </article>
        </div>
      </VPanel>
    </div>
  </main>
</template>

<style scoped>
.settings-body {
  display: grid;
  align-content: start;
  gap: 14px;
}

.settings-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);
  gap: 14px;
  align-items: start;
}

.settings-form {
  display: grid;
  gap: 16px;
}

.settings-form :deep(.el-input),
.settings-form :deep(.el-textarea) {
  width: 100%;
}

.settings-save {
  margin-left: auto;
}

.readonly-metadata {
  display: grid;
  gap: 16px;
  margin: 0;
}

.readonly-metadata dt {
  color: var(--vdw-ink-3);
  font-size: 13px;
}

.readonly-metadata dd {
  margin: 5px 0 0;
  font-size: 14px;
}

.member-count {
  margin-left: auto;
  color: var(--vdw-ink-3);
  font: 500 13px/1 var(--vdw-mono);
}

.member-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 132px auto;
  gap: 8px;
  margin-bottom: 4px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--vdw-line);
}

.member-list {
  display: grid;
}

.member-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 88px auto;
  gap: 12px;
  align-items: center;
  min-height: 48px;
  padding: 8px 0;
  border-bottom: 1px solid var(--vdw-line);
}

.member-row:last-child {
  border-bottom: 0;
}

.member-identity {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.member-identity strong {
  overflow: hidden;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.member-actions {
  display: flex;
  justify-content: flex-end;
  gap: 2px;
}
</style>
