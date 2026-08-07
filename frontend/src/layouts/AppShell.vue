<script setup lang="ts">
import {
  ExperimentOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from "@ant-design/icons-vue";
import { ArrowDown, ArrowRight } from "@element-plus/icons-vue";
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
const savedCollapsed = localStorage.getItem("vdm.sidebar-collapsed");
const collapsed = ref(
  savedCollapsed === null
    ? window.innerWidth >= 768 && window.innerWidth < 1200
    : savedCollapsed === "true",
);
const mobileOpen = ref(false);
const taskCenterOpen = ref(false);
const taskCenterUnread = ref(false);
type UserMenuCommand = "account" | "admin" | "logout";
const capabilityNoticeKey = "vdm.gpu-capability-notice-shown";

const shortcuts = computed(() =>
  resolveProjectShortcuts(recentProjects.value, fallbackProjects.value),
);
const breadcrumbs = computed(() => {
  const items = [String(route.meta.section ?? "")];
  if (
    route.path.startsWith("/projects/") &&
    route.params.id &&
    activeProject.value
  )
    items.push(activeProject.value.name);
  items.push(String(route.meta.page ?? ""));
  return items.filter(Boolean);
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
const sidebarExpanded = computed(() =>
  window.innerWidth < 768 ? mobileOpen.value : !collapsed.value,
);

function toggleSidebar() {
  if (window.innerWidth < 768) {
    mobileOpen.value = !mobileOpen.value;
    return;
  }
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
      'app-shell--mobile-open': mobileOpen,
    }"
  >
    <button
      v-if="mobileOpen"
      class="app-sidebar-backdrop"
      type="button"
      aria-label="关闭导航"
      @click="mobileOpen = false"
    />
    <aside class="app-sidebar">
      <RouterLink class="app-brand" data-test="brand" to="/overview">
        <span class="app-sidebar-icon">VDM</span>
      </RouterLink>
      <nav class="app-nav" aria-label="主导航">
        <RouterLink class="app-nav-entry" data-test="nav-overview" title="Overview" to="/overview">
          <span class="app-sidebar-icon"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 13h4v7H4zM10 4h4v16h-4zM16 9h4v11h-4z" /></svg></span>
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
              <svg aria-hidden="true" viewBox="0 0 24 24">
                <path d="M4 5h16v14H4zM8 9h8M8 13h8M8 17h5" />
              </svg>
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
            <ArrowDown v-if="projectGroupOpen" aria-hidden="true" />
            <ArrowRight v-else aria-hidden="true" />
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
              ><svg aria-hidden="true" viewBox="0 0 24 24">
                <path d="M4 7h16v12H4zM8 7V4h8v3M8 12h8M8 16h5" /></svg
            ></span>
            <span class="app-sidebar-label">模型项目</span>
          </RouterLink>
          <button
            data-test="model-project-group-toggle"
            type="button"
            aria-label="展开或收起最近模型项目"
            :aria-expanded="modelProjectGroupOpen"
            @click="toggleModelProjectGroup"
          >
            <ArrowDown v-if="modelProjectGroupOpen" aria-hidden="true" />
            <ArrowRight v-else aria-hidden="true" />
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
            ><svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="M5 5h14v14H5zM8 9h8M8 13h5M15 16h1" /></svg
          ></span>
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
              ><ExperimentOutlined aria-hidden="true"
            /></span>
            <span class="app-sidebar-label">训练任务</span>
          </RouterLink>
          <button
            data-test="training-task-group-toggle"
            type="button"
            aria-label="展开或收起最近训练任务"
            :aria-expanded="trainingTaskGroupOpen"
            @click="toggleTrainingTaskGroup"
          >
            <ArrowDown v-if="trainingTaskGroupOpen" aria-hidden="true" />
            <ArrowRight v-else aria-hidden="true" />
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
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path
                d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM5 21a7 7 0 0 1 14 0"
              />
            </svg>
          </span>
          <span class="app-sidebar-label">用户管理</span>
        </RouterLink>
        <RouterLink
          data-test="nav-llm-configs"
          title="大模型配置"
          to="/llm-configs"
        >
          <span class="app-sidebar-icon"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 6h16v12H4zM7 10h5M7 14h8M16 10h1" /></svg></span>
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
          <MenuFoldOutlined v-if="sidebarExpanded" aria-hidden="true" />
          <MenuUnfoldOutlined v-else aria-hidden="true" />
        </button>
        <nav class="app-breadcrumb" aria-label="面包屑">
          <span v-for="item in breadcrumbs" :key="item">{{ item }}</span>
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
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="m7 10 5 5 5-5" />
            </svg>
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
