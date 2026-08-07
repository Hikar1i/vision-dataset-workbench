import { createRouter, createWebHistory } from "vue-router";

import { ApiError, getAuthStatus, getCurrentUser } from "./api/auth";
import { getSetupStatus } from "./api/setup";
import AppShell from "./layouts/AppShell.vue";
import FocusLayout from "./layouts/FocusLayout.vue";
import ProjectLayout from "./layouts/ProjectLayout.vue";
import LoginView from "./views/LoginView.vue";
import AccountView from "./views/AccountView.vue";
import AnnotationWorkbenchView from "./views/AnnotationWorkbenchView.vue";
import AdminUsersView from "./views/AdminUsersView.vue";
import ProjectsView from "./views/ProjectsView.vue";
import ProjectSettingsView from "./views/ProjectSettingsView.vue";
import ProjectLabelsView from "./views/ProjectLabelsView.vue";
import ProjectDatasetsView from "./views/ProjectDatasetsView.vue";
import ProjectVideosView from "./views/ProjectVideosView.vue";
import RegisterView from "./views/RegisterView.vue";
import SetupView from "./views/SetupView.vue";

export function createAppRouter() {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: "/", redirect: "/projects" },
      { path: "/setup", component: SetupView },
      { path: "/login", component: LoginView },
      { path: "/register", component: RegisterView },
      { path: "/ready", redirect: "/projects" },
      {
        path: "/",
        component: AppShell,
        children: [
          {
            path: "projects",
            name: "projects",
            component: ProjectsView,
            meta: { section: "数据集项目", page: "全部项目" },
          },
          {
            path: "model-projects",
            name: "model-projects",
            component: () => import("./views/ModelProjectsView.vue"),
            meta: { section: "模型项目", page: "全部项目" },
          },
          {
            path: "model-projects/:id",
            name: "model-project-detail",
            component: () => import("./views/ModelProjectDetailView.vue"),
            meta: { section: "模型项目", page: "模型列表" },
          },
          {
            path: "model-projects/:id/models/:modelId",
            name: "model-detail",
            component: () => import("./views/ModelDetailView.vue"),
            meta: { section: "模型项目", page: "模型详情" },
          },
          {
            path: "hyperparameter-templates",
            name: "hyperparameter-templates",
            component: () => import("./views/HyperparameterTemplatesView.vue"),
            meta: { section: "超参数模板", page: "全部模板" },
          },
          {
            path: "hyperparameter-templates/new",
            name: "hyperparameter-template-new",
            component: () =>
              import("./views/HyperparameterTemplateEditorView.vue"),
            meta: { section: "超参数模板", page: "新建模板" },
          },
          {
            path: "hyperparameter-templates/:id",
            name: "hyperparameter-template-detail",
            component: () =>
              import("./views/HyperparameterTemplateDetailView.vue"),
            meta: { section: "超参数模板", page: "模板详情" },
          },
          {
            path: "training-tasks",
            name: "training-tasks",
            component: () => import("./views/TrainingTasksView.vue"),
            meta: { section: "训练任务", page: "全部任务" },
          },
          {
            path: "training-tasks/new",
            name: "training-task-new",
            component: () => import("./views/TrainingTaskEditorView.vue"),
            meta: { section: "训练任务", page: "新建任务" },
          },
          {
            path: "training-tasks/:id/edit",
            name: "training-task-edit",
            component: () => import("./views/TrainingTaskEditorView.vue"),
            meta: { section: "训练任务", page: "编辑草稿" },
          },
          {
            path: "training-tasks/:id",
            name: "training-task-detail",
            component: () => import("./views/TrainingTaskDetailView.vue"),
            meta: { section: "训练任务", page: "任务详情" },
          },
          {
            path: "training-tasks/:id/models/:modelId",
            name: "training-model-detail",
            component: () => import("./views/TrainingModelDetailView.vue"),
            meta: { section: "训练任务", page: "模型训练详情" },
          },
          {
            path: "projects/:id",
            component: ProjectLayout,
            children: [
              { path: "", redirect: { name: "project-videos" } },
              {
                path: "videos",
                name: "project-videos",
                component: ProjectVideosView,
                meta: { section: "数据集项目", page: "原始数据" },
              },
              {
                path: "labels",
                name: "project-labels",
                component: ProjectLabelsView,
                meta: { section: "数据集项目", page: "标签管理" },
              },
              {
                path: "datasets",
                name: "project-datasets",
                component: ProjectDatasetsView,
                meta: { section: "数据集项目", page: "数据集管理" },
              },
              {
                path: "settings",
                name: "project-settings",
                component: ProjectSettingsView,
                meta: { section: "数据集项目", page: "项目设置" },
              },
            ],
          },
          {
            path: "account",
            component: AccountView,
            meta: { section: "系统", page: "账号设置" },
          },
          {
            path: "admin/users",
            component: AdminUsersView,
            meta: { section: "系统管理", page: "用户管理" },
          },
          {
            path: "llm-configs",
            name: "llm-configs",
            component: () => import("./views/LLMConfigsView.vue"),
            meta: { section: "系统", page: "大模型配置" },
          },
        ],
      },
      {
        path: "/projects/:id/videos/:videoId/annotation",
        component: FocusLayout,
        children: [
          {
            path: "",
            name: "video-annotation",
            component: AnnotationWorkbenchView,
            meta: { section: "数据集项目", page: "在线标注" },
          },
        ],
      },
    ],
  });
  router.beforeEach(async (to) => {
    const { initialized } = await getSetupStatus();
    if (!initialized && to.path !== "/setup") return "/setup";
    if (!initialized) return;

    const authStatus = await getAuthStatus();
    let user = null;
    try {
      user = await getCurrentUser();
    } catch (reason) {
      if (!(reason instanceof ApiError) || reason.status !== 401) throw reason;
    }

    if (!user) {
      if (to.path === "/login") return;
      if (to.path === "/register" && authStatus.registration_enabled) return;
      return "/login";
    }
    if (to.path === "/setup" || to.path === "/login" || to.path === "/register")
      return "/projects";
    if (to.path.startsWith("/admin/") && !user.is_system_admin)
      return "/projects";
  });
  return router;
}
