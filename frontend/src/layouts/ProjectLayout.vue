<script setup lang="ts">
/**
 * 数据集项目外框。
 *
 * 重构前这里渲染一层"项目身份 + 页签"横栏，四个子页各自再渲染一个 PageHeader，
 * 于是项目页有两层头部，而其它页面只有一层——这是布局割裂最明显的一处。
 *
 * 现在本布局渲染**唯一**的 PageHeader：项目身份进 eyebrow，项目名是 h1，
 * 四个页签在头部底边（与全系统同位置）。子页通过 Teleport 把自己的统计与
 * 操作按钮送进这个头部，不再自建头部。
 */
import { ref, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import { getProject, type Project } from '../api/projects'
import PageHeader from '../components/PageHeader.vue'
import { provideProjectHeaderHost } from '../ui/projectHeaderHost'

provideProjectHeaderHost()

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
  <section class="content-page project-shell">
    <PageHeader
      v-if="project"
      data-test="project-context"
      :title="project.name"
      kind="project"
      :code="project.id.slice(0, 6).toUpperCase()"
      back-to="/projects"
      back-label="返回数据集项目"
    >
      <template #eyebrow>
        <span class="project-role">{{ roleLabels[project.role] }}</span>
      </template>
      <template #meta>
        <!-- 子页把当前页的统计送到这里 -->
        <span id="project-page-meta" class="project-slot" />
      </template>
      <template #actions>
        <!-- 子页把当前页的操作按钮送到这里 -->
        <span id="project-page-actions" class="project-slot" />
      </template>
      <template #tabs>
        <RouterLink data-test="project-tab-videos" :to="`/projects/${project.id}/videos`">
          原始数据
        </RouterLink>
        <RouterLink data-test="project-tab-labels" :to="`/projects/${project.id}/labels`">
          标签管理
        </RouterLink>
        <RouterLink data-test="project-tab-datasets" :to="`/projects/${project.id}/datasets`">
          数据集管理
        </RouterLink>
        <RouterLink data-test="project-tab-settings" :to="`/projects/${project.id}/settings`">
          项目设置
        </RouterLink>
      </template>
    </PageHeader>

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

/* 高度必须小于 eyebrow 的 22px 定高，否则会把该行撑开，
   数据集项目的 header 就会比其它页面高——这正是要消除的问题。 */
.project-role {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 7px;
  color: var(--vdw-ink-2);
  font-size: 13px;
  letter-spacing: 0.06em;
  background: var(--vdw-surface-3);
  border: 1px solid var(--vdw-line);
  border-radius: 999px;
}

/* 目标容器本身不占空间，内容由子页 Teleport 填充 */
.project-slot {
  display: contents;
}
</style>
