# Vision Dataset Workbench

面向视觉数据集生产流程的工作台。项目将以遗留的单机视频数据集管理工具为业务参考，先重构视频导入、下载、采样、抽帧、筛选、分组和导出主链路，再建设多用户权限、图片数据集、在线标注和模型自动标注能力。

## 当前状态

项目已完成遗留系统分析、总体重构设计、首次初始化、账号认证、项目成员权限，以及视频导入主链路。FastAPI 已提供本地/远程视频导入、持久任务、播放与下载 API，独立 Worker 负责文件复制和 yt-dlp 下载，Vue 3 已提供项目视频工作区、导入确认和任务管理界面。

已实现：

- 一次性终端口令保护的首次初始化。
- 限制在服务启动用户 `~` 内的目录浏览和新建目录。
- 原子创建 `.vision-dataset-workbench`、初始管理员和工作区定位文件。
- 默认多用户、可切换单用户的账号密码认证。
- 注册申请、管理员审批、账号禁用/启用和离线管理员密码重置。
- 12 小时空闲/7 天绝对有效期的 HttpOnly 服务端会话，以及浏览器同源写保护。
- 默认私有的视频项目、永久所有者以及 editor/viewer 成员权限。
- 项目元数据乐观并发控制，以及多用户隔离和单用户管理员兼容访问。
- 认证后的 `~` 文件浏览、新建目录和一级视频目录扫描；工作区目录不会暴露在浏览结果中。
- 本地视频完整 SHA-256 去重、远程视频 extractor/原始 ID 项目内去重，以及保留原容器扩展名的受管存储。
- SQLite 持久复制/下载任务、租约恢复、取消、重试、进度与错误记录。
- 独立 Python Worker；复制和下载分别全局并发 2、同类型每用户并发 1。
- HTTP/HTTPS 单视频与播放列表预览，及可选实例级 yt-dlp 代理和 Netscape Cookie 文件。
- owner/editor 可导入，viewer 可查看、播放和下载原始视频但不能导入或管理任务。
- Python 3.12/FastAPI 与 Vue 3/TypeScript/Vite 项目骨架。

下一阶段：

- 采样策略、抽帧、帧筛选和任务事件推送。
- 标注批次、数据集导出和审计记录。
- GPU 能力检测、自动标注和模型训练功能降级。

## 开发启动

```bash
cd backend
uv sync --python 3.12 --dev
uv run uvicorn vision_dataset_workbench.main:app --app-dir src --reload --port 38000

# 另一个终端
cd backend
uv run python -m vision_dataset_workbench.worker

# 另一个终端
cd frontend
npm install
npm run dev
```

浏览器打开 `http://127.0.0.1:35173`，输入后端终端显示的一次性口令，选择工作区父目录并创建首个管理员；初始化后使用该账号登录。前端开发服务器默认把 `/api` 代理到 `http://127.0.0.1:38000`。视频处理还要求系统可执行 `ffmpeg` 和 `ffprobe`；API 与 Worker 必须指向同一工作区。

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
