<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { ApiError } from '../api/auth'
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
import PageHeader from '../components/PageHeader.vue'

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
</script>

<template>
  <main class="settings-shell">
    <PageHeader title="项目设置">
      <template #meta><span data-test="page-stat">{{ members.length }} 位成员</span></template>
    </PageHeader>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <div v-loading="loading" class="settings-grid">
      <section v-if="project" class="panel metadata-panel">
        <header>
          <span class="section-code">PROJECT / METADATA</span>
          <h2>项目信息</h2>
        </header>

        <el-form v-if="canEdit" label-position="top">
          <el-form-item label="项目名称">
            <el-input v-model="name" data-test="project-name" maxlength="128" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input
              v-model="description"
              data-test="project-description"
              type="textarea"
              :rows="4"
              maxlength="2000"
            />
          </el-form-item>
          <el-button
            data-test="save-project"
            type="primary"
            :loading="saving"
            :disabled="!name.trim()"
            @click="saveProject"
          >
            保存项目信息
          </el-button>
        </el-form>

        <dl v-else class="readonly-metadata">
          <div><dt>名称</dt><dd>{{ project.name }}</dd></div>
          <div><dt>描述</dt><dd>{{ project.description || '暂无描述' }}</dd></div>
        </dl>
      </section>

      <section v-if="project" class="panel members-panel">
        <header class="members-heading">
          <div>
            <span class="section-code">ACCESS / MEMBERS</span>
            <h2>项目成员</h2>
          </div>
          <span>{{ members.length }} 人</span>
        </header>

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
          <el-button
            data-test="add-member"
            native-type="submit"
            type="primary"
            :loading="changingMember === 'new'"
            :disabled="!memberUsername.trim()"
          >
            添加成员
          </el-button>
        </form>

        <div class="member-list">
          <article v-for="member in members" :key="member.id" class="member-row">
            <div>
              <strong>{{ member.username }}</strong>
              <span>{{ member.status }}</span>
            </div>
            <span class="role-mark" :data-role="member.role">{{ roleLabels[member.role] }}</span>
            <div v-if="canManageMembers && member.role !== 'owner'" class="member-actions">
              <el-button
                text
                :loading="changingMember === member.id"
                @click="toggleRole(member)"
              >
                {{ member.role === 'editor' ? '改为只读' : '改为编辑者' }}
              </el-button>
              <el-button
                :data-test="`remove-${member.id}`"
                text
                type="danger"
                :disabled="changingMember === member.id"
                @click="remove(member)"
              >
                移除
              </el-button>
            </div>
          </article>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.settings-shell {
  min-height: 100%;
  padding: 22px;
  color: var(--vdw-ink);
  background: var(--vdw-canvas);
}
.settings-shell :deep(.page-header) {
  margin: -22px -22px 22px;
}
.section-code {
  color: var(--vdw-teal);
  font-family: var(--vdw-mono);
  font-size: 13px;
  letter-spacing: 0.1em;
}
.panel .section-code {
  color: var(--vdw-info);
}

.settings-grid {
  display: grid;
  grid-template-columns: minmax(300px, 0.8fr) minmax(460px, 1.2fr);
  gap: 26px;
  margin-top: 0;
}

.panel {
  padding: 29px;
  background: white;
  border: 1px solid #d8dee6;
}

.panel h2 {
  margin: 10px 0 24px;
  font-size: 25px;
  letter-spacing: -0.025em;
}

.metadata-panel .el-button {
  width: 100%;
}

.readonly-metadata {
  display: grid;
  gap: 24px;
  margin: 0;
}

.readonly-metadata div {
  display: grid;
  gap: 6px;
}

.readonly-metadata dt {
  color: #687482;
  font-size: 13px;
}

.readonly-metadata dd {
  margin: 0;
  line-height: 1.6;
}

.members-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.members-heading > span {
  color: #687482;
  font-size: 14px;
}

.member-form {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) 120px auto;
  gap: 11px;
  margin-bottom: 22px;
  padding: 18px;
  background: #f4f7fa;
  border: 1px solid #d8dee6;
}

.member-row {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) 90px minmax(170px, auto);
  gap: 18px;
  align-items: center;
  min-height: 64px;
  border-top: 1px solid #e6eaf0;
}

.member-row > div:first-child {
  display: flex;
  gap: 11px;
  align-items: baseline;
}

.member-row > div:first-child span {
  color: #687482;
  font-size: 12px;
}

.member-actions {
  display: flex;
  justify-content: flex-end;
}

.role-mark {
  width: fit-content;
  padding: 4px 7px;
  color: #3f4c59;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  border: 1px solid #cbd3dd;
}

.role-mark[data-role='owner'] {
  color: #0f6c59;
  border-color: #78cdb6;
}

@media (max-width: 900px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 620px) {
  .page-heading,
  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .topbar {
    padding-top: 18px;
    padding-bottom: 18px;
  }

  .member-form,
  .member-row {
    grid-template-columns: 1fr;
  }

  .member-actions {
    justify-content: flex-start;
  }
}
</style>
