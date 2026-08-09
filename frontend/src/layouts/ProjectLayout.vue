<script setup lang="ts">
import { ArrowLeft } from '@element-plus/icons-vue'
import { ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import { getProject, type Project } from '../api/projects'

const route = useRoute()
const emit = defineEmits<{ 'project-loaded': [project: Project] }>()
const project = ref<Project>()
const loading = ref(false)
const error = ref('')
const roleLabels = { owner: '所有者', editor: '编辑者', viewer: '只读' } as const

function setProject(value: Project) {
  project.value = value
  emit('project-loaded', value)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    setProject(await getProject(String(route.params.id)))
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '项目加载失败'
  } finally {
    loading.value = false
  }
}

watch(() => route.params.id, load, { immediate: true })
</script>

<template>
  <section class="project-shell">
    <header v-if="project" class="project-context" data-test="project-context">
      <div class="project-context-identity">
        <RouterLink class="project-context-back" to="/projects" aria-label="返回数据集项目" title="返回数据集项目">
          <el-icon><ArrowLeft /></el-icon>
        </RouterLink>
        <code>PROJECT / {{ project.id.slice(0, 6).toUpperCase() }}</code>
        <strong :title="project.name">{{ project.name }}</strong>
        <span>{{ roleLabels[project.role] }}</span>
      </div>
      <nav aria-label="项目页面">
        <RouterLink data-test="project-tab-videos" :to="`/projects/${project.id}/videos`">原始数据</RouterLink>
        <RouterLink data-test="project-tab-labels" :to="`/projects/${project.id}/labels`">标签管理</RouterLink>
        <RouterLink data-test="project-tab-datasets" :to="`/projects/${project.id}/datasets`">数据集管理</RouterLink>
        <RouterLink data-test="project-tab-settings" :to="`/projects/${project.id}/settings`">项目设置</RouterLink>
      </nav>
    </header>
    <div v-if="loading" class="state-panel">正在加载项目…</div>
    <div v-else-if="error" class="state-panel state-panel--error">{{ error }}</div>
    <RouterView v-else-if="project" v-slot="{ Component }">
      <Transition name="page-fade" mode="out-in">
        <component
          :is="Component"
          :key="String(route.name)"
          :project="project"
          @project-updated="setProject"
        />
      </Transition>
    </RouterView>
  </section>
</template>

<style scoped>
.project-shell {
  min-height: 100%;
}

.project-context {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  height: var(--vdm-project-context-height);
  padding: 0 24px;
  background: var(--vdw-surface-raised);
  border-bottom: 1px solid var(--vdw-rule);
}

.project-context-identity,
.project-context nav {
  display: flex;
  align-items: center;
  gap: 13px;
  min-width: 0;
  white-space: nowrap;
}

.project-context-back {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  color: var(--vdw-muted);
  text-decoration: none;
  background: var(--vdw-surface);
  border: 1px solid var(--vdw-rule);
  border-radius: var(--vdm-radius-control);
  transition: color var(--vdm-motion-fast) ease, border-color var(--vdm-motion-fast) ease, background-color var(--vdm-motion-fast) ease;
}

.project-context-back:hover {
  color: var(--vdw-teal-hover);
  background: #f0f7f5;
  border-color: #9fc9bf;
}

.project-context-identity code {
  color: var(--vdw-teal);
  font: 13px var(--vdw-mono);
}

.project-context-identity strong {
  overflow: hidden;
  font-size: 16px;
  text-overflow: ellipsis;
}

.project-context-identity span {
  color: var(--vdw-muted);
  font-size: 14px;
}

.project-context nav {
  align-self: center;
  gap: 4px;
  padding: 4px;
  background: #edf3f6;
  border: 1px solid #d8e3e8;
  border-radius: var(--vdm-radius-card);
}

.project-context nav a {
  display: grid;
  place-items: center;
  min-height: 38px;
  padding: 0 14px;
  color: var(--vdw-muted);
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  border: 1px solid transparent;
  border-radius: var(--vdm-radius-control);
  transition: color var(--vdm-motion-fast) ease, background-color var(--vdm-motion-fast) ease, border-color var(--vdm-motion-fast) ease, box-shadow var(--vdm-motion-fast) ease;
}

.project-context nav a:hover {
  color: var(--vdw-ink);
  background: rgb(255 255 255 / 60%);
}

.project-context nav a.router-link-active {
  color: var(--vdw-teal-hover);
  background: var(--vdw-surface-raised);
  border-color: #c8d8df;
  box-shadow: 0 2px 7px rgb(24 43 55 / 10%);
}
</style>
