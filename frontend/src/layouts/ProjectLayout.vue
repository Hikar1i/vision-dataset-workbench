<script setup lang="ts">
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
        <code>PROJECT / {{ project.id.slice(0, 6).toUpperCase() }}</code>
        <strong :title="project.name">{{ project.name }}</strong>
        <span>{{ roleLabels[project.role] }}</span>
      </div>
      <nav aria-label="项目页面">
        <RouterLink data-test="project-tab-videos" :to="`/projects/${project.id}/videos`">原始数据</RouterLink>
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
  padding: 0 18px;
  background: white;
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

.project-context-identity code {
  color: var(--vdw-teal);
  font: 12px var(--vdw-mono);
}

.project-context-identity strong {
  overflow: hidden;
  font-size: 15px;
  text-overflow: ellipsis;
}

.project-context-identity span {
  color: var(--vdw-muted);
  font-size: 13px;
}

.project-context nav {
  align-self: stretch;
}

.project-context nav a {
  display: grid;
  place-items: center;
  color: var(--vdw-muted);
  font-size: 14px;
  text-decoration: none;
  border-bottom: 2px solid transparent;
}

.project-context nav a.router-link-active {
  color: var(--vdw-teal);
  border-bottom-color: var(--vdw-teal);
}
</style>
