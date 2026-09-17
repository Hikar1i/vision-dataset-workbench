# 部署

状态：API、前端和独立 Worker 开发启动命令已实现；systemd、Windows 启动器和 Docker Compose 部署产物尚未实现。

## 目标部署

主部署位于一台部门 Linux 服务器，同时正式支持 Windows 本地实例和 Docker Compose。系统使用 SQLite 和同机持久 Worker，不支持跨服务器任务。

无论最终采用单机还是多节点，部署至少包含：

- Vue 静态资源与 FastAPI 服务。
- 独立任务 Worker。
- 工作区 SQLite。
- 受控媒体存储。
- FFmpeg/ffprobe；远程下载功能还需要 yt-dlp 及网络配置。
- 本地自动标注、训练、ONNX CUDA 推理和 TensorRT 构建还需要 `gpu` extra、NVIDIA 驱动和已入库的 YOLO `.pt` 文件；远程自动标注要求 API 与 Worker 均可访问用户配置的 X-AnyLabeling Server。

`gpu` extra 锁定 ONNX、ONNX Slim、ONNX Runtime GPU 与 TensorRT Python 包。TensorRT wheel 自带的 CUDA 主版本必须与部署主机兼容；安装成功不等于可用，启动能力检查会实际创建 TensorRT Builder。检查失败时 API 正常启动，但 TensorRT 转换和运行保持禁用，不允许 Ultralytics 在业务请求中自动安装依赖。生产部署优先使用与主机驱动、CUDA、TensorRT 明确匹配的 NVIDIA 容器镜像。

ONNX 是可下载和可复用的通用转换产物；TensorRT `.engine` 绑定构建时的 GPU、驱动、CUDA、TensorRT 与构建参数，只保证在当前构建主机使用，不作为跨设备交付格式。转换、视频推理、测试集导入和评估由 Worker 执行，API 与 Worker 必须挂载同一工作区；评估 ZIP 上限 1 GB，解压后上限 5 GB，部署时需据此设置反向代理请求体限制和工作区磁盘告警。

- Linux 原生使用两个 systemd 服务管理 API 与 Worker。
- Windows 本地使用一个启动器管理两个子进程。
- Docker Compose 使用 API 和 Worker 服务，共享本机工作区挂载。
- Docker 基础配置不要求 GPU 且不应因未声明 GPU 资源而启动失败；可选 GPU 配置需要为 API 和 Worker 安装包含 PyTorch、torchvision 与 Ultralytics 的 `gpu` extra，并向两者暴露同一设备视图。API 负责能力检测和单张交互推理，Worker 负责批量推理和训练子进程，因此不能只给其中一个进程安装依赖或暴露 GPU。

当前可按[环境与启动](08-environments.md)运行 API、前端和 Worker，但尚无受进程管理器监管的正式部署产物。不应将 Vite 开发服务器或 Uvicorn `--reload` 用作长期部署。

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
- 当前不启用 CORS；浏览器通过同源前端/反向代理访问 API。
- 媒体存储和任务临时目录均受工作区根约束；外部导入只在启动用户 `~` 内解析。
- 所有运行模式都要求用户名和密码；当前不提供无认证入口。
- 当前认证使用数据库可撤销 Session，部署时不需要共享浏览器 Token；不得记录 `vdw_session` Cookie 或数据库中的 token 摘要。
- 当前同源校验直接使用请求 scheme 与 Host，不支持可信代理头。引入 TLS 终止代理前必须先明确并测试代理边界。
- `YTDLP_PROXY` 可配置实例级代理，`YTDLP_COOKIE_FILE` 可指向 Netscape Cookie 文件；二者可能包含敏感信息，不得写入日志或仓库。
- 生产远程下载采用一个由运维维护的共享下载账号。运维人员在主机上的专用浏览器配置中交互登录目标站点，确认登录有效后导出 Netscape `cookies.txt`；普通业务用户不上传 Cookie，服务也不内置无界面浏览器或映射日常浏览器配置目录。Cookie 到期时重复登录、导出和替换流程。
- 原生部署把 Cookie 文件放在仓库与工作区之外，权限设为 `0600`，并让 API 与 Worker 的 `YTDLP_COOKIE_FILE` 指向同一只读文件。Docker 部署应把它作为 Secret 或只读单文件挂载同时注入 API 与 Worker，例如容器内 `/run/secrets/vdw_ytdlp_cookies`；不得挂载整个浏览器配置目录。固定 `YTDLP_PROXY` 可保持下载出口稳定；显式 User-Agent 注入尚未实现，遇到站点绑定 User-Agent 时必须先用实际 yt-dlp 链路验证，不能假定仅有 Cookie 即可长期工作。
- 运维流程以 [yt-dlp Cookie FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp) 和 [Docker Compose Secrets](https://docs.docker.com/compose/how-tos/use-secrets/) 为准；Cookie 文件按凭据管理和轮换，不进入普通配置备份、日志或问题截图。
- 用户配置的 X-AnyLabeling Server 和在线大模型 API 密钥均使用工作区 Fernet 密钥加密后写入数据库。未设置 `VDW_CREDENTIAL_ENCRYPTION_KEY` 时，应用原子生成并复用 `<workspace>/config/credential.key`；应随工作区备份该权限为 `0600` 的文件，API 与 Worker 必须挂载同一工作区。也可显式设置环境变量覆盖自动密钥。
- 可用 `cd backend && uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 生成显式部署密钥。轮换前必须先重新加密或清除现有用户凭据；直接替换环境变量或删除自动密钥会使旧密文不可读。
- X-AnyLabeling Server 客户端直连用户配置的地址，不继承 `HTTP_PROXY`、`HTTPS_PROXY` 或 `ALL_PROXY`；需要跨网代理时应在网络层或服务入口统一配置。

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
- 监控转换产物、临时推理会话、保存结果和评估集占用；未保存推理会话按 24 小时访问超时由后台清理，保存结果只由用户显式删除。

## 备份与回滚

- 备份范围包含数据库、项目元数据和不可重新生成的标注/配置。
- 停止 API 和 Worker 后，可整体复制 `.vision-dataset-workbench` 备份数据库、配置、媒体、标注、模型和任务记录。
- 在线备份不能只复制 SQLite 主文件；实现后需使用 SQLite backup API 或先执行安全 checkpoint。
- 应用回滚前确认旧版本能读取迁移后 schema；不能兼容时使用预先验证的数据恢复流程。
- 回滚不得简单删除正在运行任务的输出目录；先停止领取并核对任务租约。

恢复时间目标、恢复点目标和数据保留周期：`Unknown`，需由部署所有者确认。
