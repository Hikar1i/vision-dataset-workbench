<script setup lang="ts">
import {
  ArrowDown,
  ArrowRight,
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
import { computed, onMounted, ref } from "vue";
import { ElNotification } from "element-plus";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";

import { getCurrentUser, logout, type CurrentUser } from "../api/auth";
import { getCapabilities } from "../api/capabilities";
import { listProjects, type Project } from "../api/projects";
import { listModelProjects, type ModelProject } from "../api/models";
import { listTrainingTasks, type TrainingTask } from "../api/training";
import TaskCenterDrawer from "../components/TaskCenterDrawer.vue";
import {
  forgetProject,
  readRecentProjects,
  rememberProject,
  resolveProjectShortcuts,
} from "../navigation/recentProjects";
import {
  readRecentResources,
  resolveRecentResources,
} from "../navigation/recentResources";
import { clearRecentRows } from "../ui/recentRows";

const route = useRoute();
const router = useRouter();
const user = ref<CurrentUser>();
const fallbackProjects = ref<Project[]>([]);
const activeProject = ref<Project>();
const recentProjects = ref(readRecentProjects());
const projectGroupOpen = ref(
  localStorage.getItem("vdm.nav-projects-open") !== "false",
);
const modelProjectGroupOpen = ref(
  localStorage.getItem("vdm.nav-model-projects-open") !== "false",
);
const recentModelProjects = ref(
  readRecentResources("vdm.recent-model-projects"),
);
const fallbackModelProjects = ref<ModelProject[]>([]);
const trainingTaskGroupOpen = ref(
  localStorage.getItem("vdm.nav-training-tasks-open") !== "false",
);
const recentTrainingTasks = ref(
  readRecentResources("vdm.recent-training-tasks"),
);
const fallbackTrainingTasks = ref<TrainingTask[]>([]);
const collapsed = ref(
  localStorage.getItem("vdm.sidebar-collapsed") === "true",
);
const taskCenterOpen = ref(false);
const taskCenterUnread = ref(false);
type UserMenuCommand = "account" | "admin" | "logout";
const capabilityNoticeKey = "vdm.gpu-capability-notice-shown";

const shortcuts = computed(() =>
  resolveProjectShortcuts(recentProjects.value, fallbackProjects.value),
);
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
const modelProjectShortcuts = computed(() => {
  return resolveRecentResources(
    recentModelProjects.value,
    fallbackModelProjects.value,
  );
});
const trainingTaskShortcuts = computed(() =>
  resolveRecentResources(recentTrainingTasks.value, fallbackTrainingTasks.value),
);
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
  rememberProject(project);
}

function projectDeleted(projectId: string) {
  recentProjects.value = forgetProject(projectId);
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

function taskSettled() {
  window.dispatchEvent(new Event("vdm:tasks-settled"));
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
  const [currentUser, projects, modelProjects, trainingTasks] = await Promise.all([
    getCurrentUser(),
    listProjects(1, 5),
    listModelProjects(),
    listTrainingTasks(),
  ]);
  user.value = currentUser;
  fallbackProjects.value = projects.items;
  fallbackModelProjects.value = modelProjects;
  fallbackTrainingTasks.value = trainingTasks;
  await showCapabilityWarning();
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
          data-test="task-center"
          type="button"
          @click="taskCenterOpen = true"
        >
          任务中心<span
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
