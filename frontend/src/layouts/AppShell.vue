<script setup lang="ts">
import {
  ArrowDown,
  ArrowRight,
  Bell,
  Box,
  Cpu,
  DataAnalysis,
  Expand,
  Files,
  Fold,
  Operation,
  Setting,
  User,
} from "@element-plus/icons-vue";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { ElNotification } from "element-plus";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";

import { getCurrentUser, logout, type CurrentUser } from "../api/auth";
import { getCapabilities } from "../api/capabilities";
import { listProjects, type Project } from "../api/projects";
import { listModelProjects, type ModelProject } from "../api/models";
import { listTrainingTasks, type TrainingTask } from "../api/training";
import TaskCenterDrawer from "../components/TaskCenterDrawer.vue";
import { clearRecentRows } from "../ui/recentRows";
import type { GlobalProjectTask } from "../api/media";

const route = useRoute();
const router = useRouter();
const user = ref<CurrentUser>();
const fallbackProjects = ref<Project[]>([]);
const activeProject = ref<Project>();
const projectGroupOpen = ref(
  localStorage.getItem("vdm.nav-projects-open") !== "false",
);
const modelProjectGroupOpen = ref(
  localStorage.getItem("vdm.nav-model-projects-open") !== "false",
);
const fallbackModelProjects = ref<ModelProject[]>([]);
const trainingTaskGroupOpen = ref(
  localStorage.getItem("vdm.nav-training-tasks-open") !== "false",
);
const fallbackTrainingTasks = ref<TrainingTask[]>([]);
const collapsed = ref(
  localStorage.getItem("vdm.sidebar-collapsed") === "true",
);
const taskCenterOpen = ref(false);
const taskCenterUnread = ref(false);
const taskBellPulse = ref(false);
let taskBellTimer: number | undefined;
let shortcutLoadVersion = 0;
type UserMenuCommand = "account" | "admin" | "logout";
const capabilityNoticeKey = "vdm.gpu-capability-notice-shown";

const timestamp = (value: string | null | undefined) => Date.parse(value ?? "") || 0;
const shortcuts = computed(() => [...fallbackProjects.value]
  .sort((a, b) => timestamp(b.updated_at) - timestamp(a.updated_at))
  .slice(0, 5));
const sectionDestinations: Record<string, string> = {
  Overview: "/overview",
  数据集项目: "/projects",
  模型项目: "/model-projects",
  超参数模板: "/hyperparameter-templates",
  训练任务: "/training-tasks",
  系统管理: "/admin/users",
};
const breadcrumbs = computed(() => {
  const section = String(route.meta.section ?? "");
  const items: Array<{ label: string; to?: string }> = [];
  if (section) items.push({ label: section, to: sectionDestinations[section] });
  if (
    route.path.startsWith("/projects/") &&
    route.params.id &&
    activeProject.value
  )
    items.push({
      label: activeProject.value.name,
      to: `/projects/${route.params.id}/videos`,
    });
  const page = String(route.meta.page ?? "");
  if (page && page !== section) items.push({ label: page });
  return items;
});
const modelProjectShortcuts = computed(() => [...fallbackModelProjects.value]
  .sort((a, b) => timestamp(b.updated_at) - timestamp(a.updated_at))
  .slice(0, 5));
const trainingTaskShortcuts = computed(() => [...fallbackTrainingTasks.value]
  .sort((a, b) => (
    timestamp(b.last_run_at ?? b.updated_at) - timestamp(a.last_run_at ?? a.updated_at)
  ))
  .slice(0, 5));
const sidebarExpanded = computed(() => !collapsed.value);

function toggleSidebar() {
  collapsed.value = !collapsed.value;
  localStorage.setItem("vdm.sidebar-collapsed", String(collapsed.value));
}

function toggleProjectGroup() {
  projectGroupOpen.value = !projectGroupOpen.value;
  localStorage.setItem("vdm.nav-projects-open", String(projectGroupOpen.value));
}

function toggleModelProjectGroup() {
  modelProjectGroupOpen.value = !modelProjectGroupOpen.value;
  localStorage.setItem(
    "vdm.nav-model-projects-open",
    String(modelProjectGroupOpen.value),
  );
}
function toggleTrainingTaskGroup() {
  trainingTaskGroupOpen.value = !trainingTaskGroupOpen.value;
  localStorage.setItem(
    "vdm.nav-training-tasks-open",
    String(trainingTaskGroupOpen.value),
  );
}

function projectLoaded(project: Project) {
  activeProject.value = project;
  fallbackProjects.value = [
    project,
    ...fallbackProjects.value.filter((item) => item.id !== project.id),
  ];
}

function projectDeleted(projectId: string) {
  fallbackProjects.value = fallbackProjects.value.filter(
    (project) => project.id !== projectId,
  );
  if (activeProject.value?.id === projectId) activeProject.value = undefined;
}

async function signOut() {
  await logout();
  clearRecentRows();
  await router.replace("/login");
}

async function handleUserMenu(command: UserMenuCommand) {
  if (command === "account") {
    await router.push("/account");
  } else if (command === "admin") {
    await router.push("/admin/users");
  } else {
    await signOut();
  }
}

function terminalSummary(tasks: GlobalProjectTask[]) {
  const names = tasks.slice(0, 3).map((task) => task.resource_name);
  return `${names.join("、")}${tasks.length > 3 ? ` 等 ${tasks.length} 项` : ""}`;
}

function taskSettled(tasks: GlobalProjectTask[]) {
  taskBellPulse.value = true;
  if (taskBellTimer !== undefined) window.clearTimeout(taskBellTimer);
  taskBellTimer = window.setTimeout(() => {
    taskBellPulse.value = false;
    taskBellTimer = undefined;
  }, 1100);
  const succeeded = tasks.filter((task) => task.status === "succeeded");
  const failed = tasks.filter((task) => task.status === "failed");
  if (succeeded.length) {
    ElNotification.success({
      title: succeeded.length === 1 ? "后台任务已完成" : `${succeeded.length} 个后台任务已完成`,
      message: terminalSummary(succeeded),
      duration: 4500,
      position: "top-right",
    });
  }
  if (failed.length) {
    ElNotification.error({
      title: failed.length === 1 ? "后台任务执行失败" : `${failed.length} 个后台任务执行失败`,
      message: terminalSummary(failed),
      duration: 8000,
      position: "top-right",
    });
  }
  window.dispatchEvent(new Event("vdm:tasks-settled"));
  void refreshResourceShortcuts();
}

async function refreshResourceShortcuts() {
  const version = ++shortcutLoadVersion;
  try {
    const [projects, modelProjects, trainingTasks] = await Promise.all([
      listProjects(1, 5),
      listModelProjects(),
      listTrainingTasks(),
    ]);
    if (version !== shortcutLoadVersion) return;
    fallbackProjects.value = projects.items;
    fallbackModelProjects.value = modelProjects;
    fallbackTrainingTasks.value = trainingTasks;
  } catch {
    // 侧栏刷新失败时保留上次成功数据，主页面负责呈现具体错误。
  }
}

async function showCapabilityWarning() {
  if (sessionStorage.getItem(capabilityNoticeKey)) return;
  try {
    const capabilities = await getCapabilities();
    const reason =
      capabilities.gpu.reason ??
      capabilities.features.yolo_auto_annotation.reason ??
      capabilities.features.model_training.reason;
    if (!reason) return;
    sessionStorage.setItem(capabilityNoticeKey, "true");
    ElNotification.warning({
      title: "部分 GPU 功能未启用",
      message: reason,
      duration: 0,
      position: "top-right",
    });
  } catch {
    // 能力提示不应阻止主界面加载。
  }
}

onMounted(async () => {
  const [currentUser] = await Promise.all([
    getCurrentUser(),
    refreshResourceShortcuts(),
  ]);
  user.value = currentUser;
  await showCapabilityWarning();
});
watch(() => route.fullPath, () => void refreshResourceShortcuts());
onUnmounted(() => {
  if (taskBellTimer !== undefined) window.clearTimeout(taskBellTimer);
});
</script>

<template>
  <div
    class="app-shell"
    :class="{
      'app-shell--collapsed': collapsed,
    }"
  >
    <aside class="app-sidebar">
      <RouterLink class="app-brand" data-test="brand" to="/overview">
        <span class="app-sidebar-icon">VDM</span>
      </RouterLink>
      <nav class="app-nav" aria-label="主导航">
        <RouterLink class="app-nav-entry" data-test="nav-overview" title="Overview" to="/overview">
          <span class="app-sidebar-icon"><el-icon><DataAnalysis /></el-icon></span>
          <span class="app-sidebar-label">Overview</span>
        </RouterLink>
        <div class="app-nav-group">
          <RouterLink
            class="app-nav-entry"
            data-test="nav-projects"
            title="数据集项目"
            to="/projects"
          >
            <span class="app-sidebar-icon">
              <el-icon><Files /></el-icon>
            </span>
            <span class="app-sidebar-label">数据集项目</span>
          </RouterLink>
          <button
            data-test="project-group-toggle"
            type="button"
            aria-label="展开或收起最近项目"
            :aria-expanded="projectGroupOpen"
            @click="toggleProjectGroup"
          >
            <el-icon><ArrowDown v-if="projectGroupOpen" /><ArrowRight v-else /></el-icon>
          </button>
        </div>
        <Transition name="sidebar-list">
          <div v-if="projectGroupOpen && !collapsed" class="app-nav-children">
            <RouterLink
              v-for="project in shortcuts"
              :key="project.id"
              data-test="recent-project"
              :to="`/projects/${project.id}/videos`"
              >{{ project.name }}</RouterLink
            >
          </div>
        </Transition>
        <div class="app-nav-group">
          <RouterLink
            class="app-nav-entry"
            data-test="nav-model-projects"
            title="模型项目"
            to="/model-projects"
          >
            <span class="app-sidebar-icon"
              ><el-icon><Box /></el-icon></span>
            <span class="app-sidebar-label">模型项目</span>
          </RouterLink>
          <button
            data-test="model-project-group-toggle"
            type="button"
            aria-label="展开或收起最近模型项目"
            :aria-expanded="modelProjectGroupOpen"
            @click="toggleModelProjectGroup"
          >
            <el-icon><ArrowDown v-if="modelProjectGroupOpen" /><ArrowRight v-else /></el-icon>
          </button>
        </div>
        <Transition name="sidebar-list">
          <div
            v-if="modelProjectGroupOpen && !collapsed"
            class="app-nav-children"
          >
            <RouterLink
              v-for="project in modelProjectShortcuts"
              :key="project.id"
              data-test="recent-model-project"
              :to="`/model-projects/${project.id}`"
              >{{ project.name }}</RouterLink
            >
          </div>
        </Transition>
        <RouterLink
          class="app-nav-entry"
          data-test="nav-hyperparameter-templates"
          title="超参数模板"
          to="/hyperparameter-templates"
        >
          <span class="app-sidebar-icon"
            ><el-icon><Operation /></el-icon></span>
          <span class="app-sidebar-label">超参数模板</span>
        </RouterLink>
        <div class="app-nav-group">
          <RouterLink
            class="app-nav-entry"
            data-test="nav-training-tasks"
            title="训练任务"
            to="/training-tasks"
          >
            <span class="app-sidebar-icon"
              ><el-icon><Cpu /></el-icon></span>
            <span class="app-sidebar-label">训练任务</span>
          </RouterLink>
          <button
            data-test="training-task-group-toggle"
            type="button"
            aria-label="展开或收起最近训练任务"
            :aria-expanded="trainingTaskGroupOpen"
            @click="toggleTrainingTaskGroup"
          >
            <el-icon><ArrowDown v-if="trainingTaskGroupOpen" /><ArrowRight v-else /></el-icon>
          </button>
        </div>
        <Transition name="sidebar-list">
          <div
            v-if="trainingTaskGroupOpen && !collapsed"
            class="app-nav-children"
          >
            <RouterLink
              v-for="task in trainingTaskShortcuts"
              :key="task.id"
              data-test="recent-training-task"
              :to="`/training-tasks/${task.id}`"
              >{{ task.name }}</RouterLink
            >
          </div>
        </Transition>
      </nav>
      <footer class="app-sidebar-footer">
        <RouterLink
          v-if="user?.is_system_admin"
          data-test="nav-admin-users"
          title="用户管理"
          to="/admin/users"
        >
          <span class="app-sidebar-icon">
            <el-icon><User /></el-icon>
          </span>
          <span class="app-sidebar-label">用户管理</span>
        </RouterLink>
        <RouterLink
          data-test="nav-llm-configs"
          title="大模型配置"
          to="/llm-configs"
        >
          <span class="app-sidebar-icon"><el-icon><Setting /></el-icon></span>
          <span class="app-sidebar-label">大模型配置</span>
        </RouterLink>
        <div class="app-sidebar-user" :title="user?.username">
          <span class="app-sidebar-icon"
            ><b>{{ user?.username.slice(0, 1).toUpperCase() }}</b></span
          >
          <span class="app-sidebar-label">{{ user?.username }}</span>
        </div>
      </footer>
    </aside>

    <section class="app-frame">
      <header class="app-topbar">
        <button
          data-test="sidebar-toggle"
          type="button"
          :aria-label="sidebarExpanded ? '收起侧栏' : '展开侧栏'"
          @click="toggleSidebar"
        >
          <el-icon><Fold v-if="sidebarExpanded" /><Expand v-else /></el-icon>
        </button>
        <nav class="app-breadcrumb" aria-label="面包屑">
          <template v-for="(item, index) in breadcrumbs" :key="`${item.label}-${index}`">
            <RouterLink
              v-if="item.to && index < breadcrumbs.length - 1"
              :data-test="index === 0 ? 'breadcrumb-section' : undefined"
              :to="item.to"
            >{{ item.label }}</RouterLink>
            <span
              v-else
              :data-test="index === breadcrumbs.length - 1 ? 'breadcrumb-page' : undefined"
              aria-current="page"
            >{{ item.label }}</span>
          </template>
        </nav>
        <button
          class="task-center-trigger"
          :class="{ 'is-unread': taskCenterUnread, 'is-pulsing': taskBellPulse }"
          data-test="task-center"
          type="button"
          @click="taskCenterOpen = true"
        >
          <el-icon class="task-center-bell" aria-hidden="true"><Bell /></el-icon>
          <span>任务中心</span><span
            v-if="taskCenterUnread"
            class="notification-dot"
            aria-label="有已完成任务"
          />
        </button>
        <el-dropdown
          class="user-menu"
          trigger="click"
          placement="bottom-end"
          @command="handleUserMenu"
        >
          <button class="user-menu-trigger" data-test="user-menu" type="button">
            <span>{{ user?.username }}</span>
            <el-icon><ArrowDown /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="account">账号设置</el-dropdown-item>
              <el-dropdown-item v-if="user?.is_system_admin" command="admin"
                >系统管理</el-dropdown-item
              >
              <el-dropdown-item command="logout" divided
                >退出登录</el-dropdown-item
              >
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </header>
      <main class="app-content">
        <RouterView v-slot="{ Component }">
          <Transition name="page-fade" mode="out-in">
            <component
              :is="Component"
              @project-loaded="projectLoaded"
              @project-deleted="projectDeleted"
            />
          </Transition>
        </RouterView>
      </main>
    </section>
    <TaskCenterDrawer
      v-model="taskCenterOpen"
      @unread="taskCenterUnread = $event"
      @settled="taskSettled"
    />
  </div>
</template>
