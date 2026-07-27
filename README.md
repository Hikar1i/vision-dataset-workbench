# Vision Dataset Workbench

面向视觉数据集生产流程的工作台。项目将以遗留的单机视频数据集管理工具为业务参考，先重构视频导入、下载、采样、抽帧、筛选、分组和导出主链路，再建设多用户权限、图片数据集、在线标注和模型自动标注能力。

## 当前状态

项目已完成遗留系统分析、总体重构设计、首次初始化、账号认证、项目成员权限，以及视频导入、采样、抽帧、帧筛选和项目标签管理主链路。FastAPI 提供受管媒体、帧、标签与运行能力 API，独立 Worker 负责复制、yt-dlp 下载和 FFmpeg 抽帧，Vue 3 提供项目视频工作区、标签管理、采样配置、帧筛选和任务管理界面。

已实现：

- 一次性终端口令保护的首次初始化。
- 限制在服务启动用户 `~` 内的目录浏览和新建目录。
- 原子创建 `.vision-dataset-workbench`、初始管理员和工作区定位文件。
- 默认多用户、可切换单用户的账号密码认证。
- 注册申请、管理员审批、账号禁用/启用和离线管理员密码重置。
- 12 小时空闲/7 天绝对有效期的 HttpOnly 服务端会话，以及浏览器同源写保护。
- 默认私有的视频项目、永久所有者以及 editor/viewer 成员权限。
- 项目元数据乐观并发控制，以及多用户隔离和单用户管理员兼容访问。
- 项目级英文类别、可选中文描述、颜色、0 起始映射顺序和启停管理；owner/editor 可写，viewer 只读。
- 认证后的 `~` 文件浏览、新建目录和一级视频目录扫描；工作区目录不会暴露在浏览结果中。
- 本地视频完整 SHA-256 去重、远程视频 extractor/原始 ID 项目内去重，以及保留原容器扩展名的受管存储。
- SQLite 持久复制/下载任务、租约恢复、取消、重试、进度与错误记录。
- 独立 Python Worker；复制和下载分别全局并发 2、同类型每用户并发 1。
- HTTP/HTTPS 单视频与播放列表预览，及可选实例级 yt-dlp 代理和 Netscape Cookie 文件。
- owner/editor 可导入，viewer 可查看、播放和下载原始视频但不能导入或管理任务。
- 每个视频持久保存版本化采样方案，支持目标帧数、固定帧间隔和时间间隔三种模式。
- 目标帧数模式按视频时长计算可预测结果：2 分钟及以下取短视频目标，2–10 分钟线性增长，10 分钟及以上取长视频上限。
- 抽帧任务默认全局并发 2、每用户并发 1；使用临时目录和原子替换，失败或取消不会破坏上一代帧。
- JPG/PNG 输出、稳定帧记录、帧分页浏览和带版本冲突检测的批量启停。
- viewer 可查看和下载采样帧，owner/editor 可配置、重采样和筛选帧。
- 单项目最多 999 个视频，数据库处理并发容量竞争；owner/editor 可按版本启停视频的后续标注与导出参与状态。
- 高密度视频工作台提供项目轨道、紧凑媒体台账、结构化状态信息、当前页全选以及 25/50/100/200/全部分页。
- 启动时检测 NVIDIA GPU、PyTorch CUDA、ONNX Runtime CUDA 和 Ultralytics；缺少 GPU 或依赖时保持启动并提示功能降级。
- uv 可选 `gpu` 依赖组，已在 RTX A4000 和 Quadro RTX 4000 上验证 PyTorch CUDA 12.8 与 ONNX CUDA Provider。
- Python 3.12/FastAPI 与 Vue 3/TypeScript/Vite 项目骨架。

下一阶段：

- 在线手动矩形框标注和标注记录。
- 系统内直接调用 YOLO、GroundingDINO 等模型自动标注，不依赖 X-AnyLabeling。
- 数据集导出、模型管理、训练任务和审计记录。
- 按实际交互需求评估任务事件推送；当前任务抽屉使用轮询。

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

GPU 服务器将后端安装命令改为 `uv sync --python 3.12 --dev --extra gpu`；无 GPU 实例不安装该 extra。

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
