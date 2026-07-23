# Vision Dataset Workbench

面向视觉数据集生产流程的工作台。项目将以遗留的单机视频数据集管理工具为业务参考，先重构视频导入、下载、采样、抽帧、筛选、分组和导出主链路，再建设多用户权限、图片数据集、在线标注和模型自动标注能力。

## 当前状态

项目已完成遗留系统分析、总体重构设计和首个可运行应用基础：FastAPI 提供首次初始化 API，Vue 3 提供初始化向导，Alembic 创建首个 SQLite `users` schema。任务 Worker、登录认证和数据集主流程尚未实现。

已实现：

- 一次性终端口令保护的首次初始化。
- 限制在服务启动用户 `~` 内的目录浏览和新建目录。
- 原子创建 `.vision-dataset-workbench`、初始管理员和工作区定位文件。
- Python 3.12/FastAPI 与 Vue 3/TypeScript/Vite 项目骨架。

下一阶段：

- 登录认证、运行模式、注册审批和项目权限。
- 持久任务 Worker、能力检测和 GPU 功能降级。
- 视频项目、导入、采样、抽帧、筛选、标注批次和导出。

## 开发启动

```bash
cd backend && uv sync --python 3.12 --dev
cd backend && uv run uvicorn vision_dataset_workbench.main:app --app-dir src --reload
cd frontend && npm install
cd frontend && npm run dev
```

浏览器打开 `http://127.0.0.1:5173`，输入后端终端显示的一次性口令，选择工作区父目录并创建首个管理员。前端开发服务器默认把 `/api` 代理到 `http://127.0.0.1:8000`。

验证命令见[测试策略](docs/06-testing-strategy.md)，配置和首次启动细节见[环境与启动](docs/08-environments.md)。

## 文档

- [项目背景与目标](docs/01-project-background.md)
- [架构](docs/02-architecture.md)
- [数据库](docs/03-database.md)
- [API](docs/04-api.md)
- [代码规范](docs/05-code-style.md)
- [测试策略](docs/06-testing-strategy.md)
- [部署](docs/07-deployment.md)
- [环境与启动](docs/08-environments.md)
- [已知问题](docs/09-known-issues.md)

## 本地 AI 工作区

AI 生成的调查、设计、计划和临时产物存放在 `.ai-local/`，并通过 `.git/info/exclude` 排除。用户提供的 `.ai-local/references/` 只读；长期项目文档只存放在根目录 `README.md` 和 `docs/`。
