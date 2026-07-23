# 部署

状态：开发启动命令已实现；systemd、Windows 启动器、Docker Compose 和 Worker 部署产物尚未实现。

## 目标部署

主部署位于一台部门 Linux 服务器，同时正式支持 Windows 本地实例和 Docker Compose。系统使用 SQLite 和同机持久 Worker，不支持跨服务器任务。

无论最终采用单机还是多节点，部署至少包含：

- Vue 静态资源与 FastAPI 服务。
- 独立任务 Worker。
- 工作区 SQLite。
- 受控媒体存储。
- FFmpeg/ffprobe；远程下载功能还需要 yt-dlp 及网络配置。

- Linux 原生使用两个 systemd 服务管理 API 与 Worker。
- Windows 本地使用一个启动器管理两个子进程。
- Docker Compose 使用 API 和 Worker 服务，共享本机工作区挂载。
- Docker 基础配置不要求 GPU；可选 GPU 配置只向 Worker 暴露设备。

当前只能按[环境与启动](08-environments.md)运行开发服务器，不应将 Vite 开发服务器或 Uvicorn `--reload` 用作生产部署。

## 遗留部署风险

- 遗留容器用 Flask debug server 运行后端，不是目标生产部署方式。
- 遗留 Nginx 只对 `/events/` 关闭代理缓冲，但真实 SSE 位于 `/api/.../events`。
- Python 版本在 pyproject、Docker 和 README 中分别为 3.13、3.11 和 3.8+/3.10。
- `requirements.txt` 与 `pyproject.toml` 的 Pillow 依赖不一致。
- 遗留 GitLab CI 含明文镜像仓库凭据。若凭据仍有效，应在原系统立即轮换；新项目不得复制任何值或提交密钥。

## 配置与密钥

- 所有环境差异通过环境变量或部署平台的密钥机制注入。
- 数据库密码、会话密钥、对象存储凭据、代理认证和镜像仓库凭据不得进入 Git。
- 配置启动时校验；缺失必需值时快速失败并给出变量名，不打印密钥值。
- CORS 使用明确来源白名单，不能沿用全开放配置。
- 媒体存储根、导入根和临时目录使用不同配置并验证权限。
- `single/none` 只允许 loopback，或必须配置非空 IP/CIDR 白名单。

## 发布流程要求

1. 生成可追踪版本，记录源提交和迁移版本。
2. 运行静态检查、自动化测试、前端构建和镜像扫描。
3. 备份数据库并验证备份可读。
4. 停止领取新任务或等待不兼容任务结束。
5. 执行版本化迁移。
6. 部署 API、Worker 和前端。
7. 执行健康检查和主工作流冒烟测试。
8. 恢复任务领取并观察错误率、队列和磁盘。

具体 CI/CD 平台和命令：`Unknown`。

## 健康与可观测性

- API 提供存活与就绪检查，区分进程存活、数据库可用和迁移版本正确。
- Worker 报告心跳、可处理任务类型和当前任务。
- 日志包含时间、级别、服务、请求/任务 ID 和项目 ID，不记录 Cookie、Token、完整代理 URL 或用户文件内容。
- 指标至少覆盖请求错误、任务队列长度/耗时/失败、Worker 心跳、磁盘空间和数据库连接。
- 长任务日志和最终错误需可由任务 ID 查询。

## 备份与回滚

- 备份范围包含数据库、项目元数据和不可重新生成的标注/配置。
- 停止 API 和 Worker 后，可整体复制 `.vision-dataset-workbench` 备份数据库、配置、媒体、标注、模型和任务记录。
- 在线备份不能只复制 SQLite 主文件；实现后需使用 SQLite backup API 或先执行安全 checkpoint。
- 应用回滚前确认旧版本能读取迁移后 schema；不能兼容时使用预先验证的数据恢复流程。
- 回滚不得简单删除正在运行任务的输出目录；先停止领取并核对任务租约。

恢复时间目标、恢复点目标和数据保留周期：`Unknown`，需由部署所有者确认。
