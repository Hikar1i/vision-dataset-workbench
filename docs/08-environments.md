# 环境与启动

状态：后端、前端和首次初始化可在开发环境运行；Worker、认证模式和部署启动器尚未实现。

## 当前可执行操作

安装与启动后端：

```bash
cd backend && uv sync --python 3.12 --dev
cd backend && uv run uvicorn vision_dataset_workbench.main:app --app-dir src --reload --port 38000
```

安装与启动前端：

```bash
cd frontend && npm install
cd frontend && npm run dev
```

默认地址为后端 `http://127.0.0.1:38000`、前端 `http://127.0.0.1:35173`。前端端口被占用时会直接报错，不会静默切换端口。后端未初始化时在终端输出一次性口令；前端向导使用该口令浏览启动用户的 `~`、新建目录、创建工作区和首个管理员。按 `Ctrl+C` 停止开发进程。

验证命令：

```bash
cd backend && uv run pytest
cd frontend && npm test
cd frontend && npm run build
```

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
- 未检测到 GPU 时正常启动并禁用自动标注和训练。

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

## 计划中的运行模式

```text
APP_MODE=multi|single
SINGLE_AUTH=password|token|none
VDW_WORKSPACE=<workspace-path>
```

- 默认 `multi`。
- 单用户三种认证方式与多用户共用数据库和项目成员数据。
- 模式切换后重启生效。
- `single/none` 只允许 loopback 或非空 IP 白名单。
- CLI 参数或 `VDW_WORKSPACE` 优先于平台工作区定位文件。

当前只实现了 `VDW_WORKSPACE`。`APP_MODE`、`SINGLE_AUTH`、登录和无认证 IP 限制属于下一阶段，不应在当前版本中配置。

## 配置类别

除 `VDW_WORKSPACE` 外，变量名在对应功能实现后确定；目标类别包括：

| 类别 | 内容 |
| --- | --- |
| Runtime | 环境名、日志级别、服务版本 |
| Database | 连接地址、池和迁移检查 |
| Storage | 工作区、用户 home、临时根、容量阈值 |
| Tasks | Worker 并发、租约、重试、超时 |
| Media | FFmpeg/ffprobe/yt-dlp 路径与限制 |
| Web | 绑定地址、可信代理、IP/CIDR 白名单 |
| Auth | 运行模式、会话密钥、单用户 Token |
| GPU | 能力检测、每 GPU 任务数和模型依赖 |

本地示例配置只能包含无敏感默认值；真实密钥通过未提交文件或密钥管理服务注入。

## 后续启动与停止要求

后续仍需补充可复制执行的：

- 依赖安装与版本检查。
- 独立 Worker 启动。
- 全栈容器启动。
- 原生生产进程和 Windows 启动器。

当前健康检查为 `GET /api/v1/health`。数据库由首次初始化创建；已有数据库的发布升级流程仍待实现。

## 外部工具验证

启动时应验证 FFmpeg、ffprobe 和可选 yt-dlp 的存在与版本。运行时版本必须与容器和 CI 基线一致；不得重现遗留项目中 README、pyproject 和 Docker 分别声明不同 Python 版本的情况。
