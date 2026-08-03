# 环境与启动

状态：后端、前端、首次初始化、认证模式、GPU 能力检测，以及视频导入、抽帧、模型入库和自动标注可在开发环境运行；正式部署启动器尚未实现。

## 当前可执行操作

安装与启动后端：

```bash
cd backend && uv sync --python 3.12 --dev
cd backend && uv run uvicorn vision_dataset_workbench.main:app --app-dir src --reload --port 38000
```

GPU 服务器安装可选模型运行依赖：

```bash
cd backend
uv sync --python 3.12 --dev --extra gpu
uv run python -c "import torch, ultralytics; print(torch.cuda.is_available()); print(torch.__version__, ultralytics.__version__)"
```

当前锁定组合为 PyTorch 2.9.1/torchvision 0.24.1 CUDA 12.8 和 Ultralytics 8.4.x。CUDA wheel 使用 uv 显式 PyTorch `cu128` 索引；无 GPU 实例不启用该 extra。官方兼容依据见 [uv PyTorch 指南](https://docs.astral.sh/uv/guides/integration/pytorch/)和 [PyTorch 2.9.1 CUDA 12.8 安装矩阵](https://pytorch.org/get-started/previous-versions/)。

本地自动标注时 API 和 Worker 都应从安装了 `gpu` extra 的同一 uv 环境启动：API 执行单张交互推理，Worker 执行批量推理。管理员只能登记 YOLO `.pt` 文件；源路径必须位于启动用户 `~` 内，入库后复制到工作区 `models/<model UUID>/`。模型显示 `ready` 代表复制完成，实际权重兼容性在首次推理时验证。本系统不再安装或加载本地 ONNX、Transformers 或 GroundingDINO 模型。

远程自动标注不要求本系统安装模型运行依赖。用户在标注页配置可由 API 和 Worker 访问的 X-AnyLabeling Server 地址及可选 API 密钥；客户端访问本机服务时应填写 `http://127.0.0.1:<port>`，`0.0.0.0` 只用于服务监听。当前只接收矩形结果，服务端点选、关键点、多边形等任务不会出现在可选模型列表中。

安装与启动前端：

```bash
cd frontend && npm install
cd frontend && npm run dev
```

在独立终端启动任务 Worker：

```bash
cd backend
uv run python -m vision_dataset_workbench.worker
```

默认地址为后端 `http://127.0.0.1:38000`、前端 `http://127.0.0.1:35173`。前端端口被占用时会直接报错，不会静默切换端口。后端未初始化时在终端输出一次性口令；前端向导使用该口令浏览启动用户的 `~`、新建目录、创建工作区和首个管理员。Worker 与 API 必须使用相同的 `HOME`、`VDW_WORKSPACE` 和媒体配置。按 `Ctrl+C` 停止各开发进程。

需要从局域网访问时，可显式使用 `uvicorn ... --host 0.0.0.0 --port 38000`，并让前端或反向代理保持 `/api` 同源。系统不提供 IP 白名单，访问控制依赖用户名、密码和服务端 Session。

验证命令：

```bash
cd backend && uv run pytest
cd frontend && npm test
cd frontend && npm run build
```

SQLite 版本与日志模式需在实际 API/Worker 使用的 uv 环境中核对：

```bash
cd backend
uv run python -c "import sqlite3; print(sqlite3.sqlite_version)"
uv run python -c "from vision_dataset_workbench.database import sqlite_supports_safe_wal; print(sqlite_supports_safe_wal())"
```

当前代码仅在 SQLite 3.51.3 及以上，或已确认修复的 3.44.6、3.50.7 上启用 WAL；其他版本自动使用 rollback journal。部署检查返回 `False` 时不得把实际日志模式记录为 WAL，也不应绕过该保护。

遗留项目位于 `.ai-local/references/`，只用于阅读和验证，不是新项目的启动目录。

## 首次初始化与定位

- `VDW_WORKSPACE` 可显式指定已有工作区，优先于平台定位文件。
- Linux 定位文件默认位于 `$XDG_CONFIG_HOME/vision-dataset-workbench/instance.json`，未设置时使用 `~/.config/vision-dataset-workbench/instance.json`。
- Windows 定位文件位于 `%APPDATA%/vision-dataset-workbench/instance.json`。
- 定位目标必须位于启动用户 `~` 内，且包含 `db/workbench.sqlite3`，否则应用保持未初始化状态。
- 口令只存在于当前 API 进程内；初始化失败可重试，成功后立即失效，重启未初始化实例会生成新口令。

## 计划中的环境

### Local

- Linux 或 Windows 上的前端、FastAPI、Worker 和 SQLite。
- 默认工作区为用户选择位置下的 `.vision-dataset-workbench`。
- 支持使用假下载适配器和短测试视频，无需访问真实平台即可开发主流程。
- 已实现启动时一次性 GPU/运行时探测；未检测到 GPU 时正常启动并禁用自动标注和训练。

### Test

- 每次运行创建隔离数据库和临时存储根。
- 默认禁用外部网络，使用受控 FFmpeg fixture。
- 测试结束只清理本次创建的明确路径。

### Staging

- 与生产使用相同的服务拓扑和迁移方式。
- 使用独立数据库、存储、密钥和低价值测试数据。
- 用于迁移演练、长任务恢复和升级/回滚验证。

### Production-like / Production

- 关闭 debug 和热重载。
- API 与 Worker 使用受监管的进程管理。
- 配置健康检查、日志、指标、备份和磁盘告警。
- CORS、文件导入根和代理配置使用明确白名单。

## 运行模式

```text
APP_MODE=multi|single
REGISTRATION_ENABLED=false|true
VDW_WORKSPACE=<workspace-path>
YTDLP_PROXY=<optional-proxy-url>
YTDLP_COOKIE_FILE=<optional-netscape-cookie-file>
VDW_CREDENTIAL_ENCRYPTION_KEY=<optional-fernet-key>
```

- 默认 `multi`。
- `single` 只允许初始化管理员使用用户名和密码登录。
- 两种模式共用数据库和项目成员数据。
- 模式切换后重启生效。
- `VDW_WORKSPACE` 优先于平台工作区定位文件；当前 API 启动命令没有单独的工作区 CLI 参数。
- yt-dlp 默认不使用代理或 Cookie；仅在实例确有需要时配置上述两个变量。
- `VDW_CREDENTIAL_ENCRYPTION_KEY` 用于加密用户保存的远程 API 密钥。保存带 API 密钥的配置前必须设置；API 和 Worker 必须一致。

上述六个变量均已实现。布尔值只接受 `true` 或 `false`；`APP_MODE=single` 与 `REGISTRATION_ENABLED=true` 同时出现会使应用启动失败。单用户模式启动时撤销普通用户现有会话，但保留用户和业务数据；切回多用户后有效账号可重新登录。

管理员忘记密码时，先停止 API，再在终端交互式重置；密码不会出现在命令参数中：

```bash
cd backend
uv run python -m vision_dataset_workbench.admin reset-password \
  --workspace /absolute/path/.vision-dataset-workbench \
  --username admin
```

## 配置类别

除已列出的变量外，后续变量名在对应功能实现后确定；目标类别包括：

| 类别 | 内容 |
| --- | --- |
| Runtime | 环境名、日志级别、服务版本 |
| Database | 连接地址、池和迁移检查 |
| Storage | 工作区、用户 home、临时根、容量阈值 |
| Tasks | Worker 并发、租约、重试、超时 |
| Media | FFmpeg/ffprobe/yt-dlp 路径与限制 |
| Web | 绑定地址、前端来源和 Cookie 安全属性 |
| Auth | 运行模式、注册开关和 Session 生命周期 |
| GPU | 已实现硬件/运行时能力检测、单模型进程内互斥和批量任务并发限制；设备选择、显存感知调度和尚未实现的训练调度后续补充 |

本地示例配置只能包含无敏感默认值；真实密钥通过未提交文件或密钥管理服务注入。

## 后续启动与停止要求

后续仍需补充可复制执行的：

- 依赖安装与版本检查。
- 全栈容器启动。
- 原生生产进程和 Windows 启动器。

当前健康检查为 `GET /api/v1/health`。数据库由首次初始化创建，已有工作区在应用启动时自动执行 Alembic 升级；带备份和回滚验证的正式发布流程仍待实现。

## 外部工具验证

视频导入和抽帧要求 `ffmpeg`、`ffprobe` 可执行；yt-dlp 是后端锁定的 Python 依赖。当前真实链路已验证三者可完成媒体探测、缩略图、本地复制、HTTP 下载、JPG/PNG 抽帧和重采样替换。抽帧使用兼容较旧 FFmpeg 的 `-vsync vfr`；启动时的显式能力/版本检查仍待实现。运行时版本必须与容器和 CI 基线一致；不得重现遗留项目中 README、pyproject 和 Docker 分别声明不同 Python 版本的情况。
