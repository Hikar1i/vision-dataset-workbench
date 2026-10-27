# 部署

状态：CPU/GPU Docker Compose 已实现；开发启动命令可用，原生 systemd 和 Windows 生产启动器尚未提供。部署为单机 Nginx + API + Worker + SQLite，不支持跨服务器 Worker。

从获取源码到首次登录的完整操作见 [README：容器部署](../README.md#容器部署)。本文件补充运行边界、GPU 兼容、密钥、备份与发布细节。项目文件名为 `compose.yaml`；从源码构建必须同时取得 Dockerfile、deploy、前后端源码和锁文件，不能只分发 Compose 文件。

## CPU 部署

要求 Docker Engine + Compose v2 或 Docker Desktop（Linux containers）。当前实测平台均为 Linux/amd64：Ubuntu 22.04、Windows 11、Intel macOS 15；未实测 ARM64。

```bash
cp .env.example .env
mkdir -p imports
docker compose up -d --build
docker compose ps
docker compose logs api
```

Windows PowerShell 将前两行替换为 `Copy-Item .env.example .env`、`New-Item -ItemType Directory -Force imports`。浏览器打开 `http://127.0.0.1:8080`，输入 API 日志中的一次性初始化口令，选择容器 home 内父目录并创建管理员；无默认管理员账号/密码。Worker 在首次初始化完成前等待，之后自动进入调度循环。 首次管理员密码由用户自行设置，数据库只保存密码哈希；初始化口令不是登录密码。容器/原生管理员重置命令见 [README：忘记管理员密码](../README.md#忘记管理员密码)。

CPU 镜像只安装 `backend/uv.lock` 基础依赖，包含 FFmpeg/ffprobe 和 yt-dlp，不安装 PyTorch、Ultralytics、ONNX Runtime、TensorRT 等 GPU extra。可使用视频/图像导入、抽帧、筛选、手工标注、远程自动标注、数据集导出、模型与测试集管理、历史查询和下载。本地模型自动标注、训练、转换、在线推理和评估保持禁用。远程标注和在线视觉大模型需要另行配置可达服务和凭据，不随镜像提供服务。

## NVIDIA GPU 部署

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
docker compose -f compose.yaml -f compose.gpu.yaml ps
```

- Linux 需要 NVIDIA 驱动及已配置的 NVIDIA Container Toolkit；Windows 需要支持 NVIDIA GPU 的 WSL2 Docker Desktop。Docker Desktop 的 macOS 不支持此 GPU 方式，AMD/Intel 显卡使用 CPU 配置。参见 [Docker Desktop GPU](https://docs.docker.com/desktop/features/gpu/)及 [Compose GPU 配置](https://docs.docker.com/compose/how-tos/gpu-support/)。
- 当前冻结依赖包含 PyTorch 2.9.1 CUDA 12.8、ONNX Runtime GPU 1.24.4、TensorRT 11.3.0.99 和 NVIDIA ModelOpt；TensorRT 默认 wheel 为 CUDA 13 系列，完整功能要求 NVIDIA R580 或更新的兼容驱动。仅满足 PyTorch CUDA 12.8 并不代表 TensorRT 可用，参见 [TensorRT 前提](https://docs.nvidia.com/deeplearning/tensorrt/latest/installing-tensorrt/prerequisites.html)。宿主不需要安装 CUDA Toolkit；wheel 库随 GPU 镜像安装。
- API 和 Worker 使用同一 GPU 镜像、相同全部设备视图。不能只给 Worker 暴露显卡，API 也执行交互推理及运行时检查。安装成功不等于能力可用：以系统运行能力页面中的实际探测为准。
- TensorRT FP16 strongly typed 构建使用 ModelOpt 改写 ONNX 精度；禁止 Ultralytics 在业务请求中自动安装依赖。ONNX 可作为通用产物下载；`.engine` 绑定 GPU、驱动、CUDA、TensorRT 与构建参数，只保证当前构建环境使用，不能跨设备直接分发。

## 导入、端口与持久化

`.env.example` 可配置：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `VDW_PORT` | `8080` | 唯一对外 HTTP 端口 |
| `VDW_BIND_ADDRESS` | `127.0.0.1` | 改为 `0.0.0.0` 才对局域网开放，需配合主机防火墙 |
| `VDW_IMPORTS` | `./imports` | 宿主导入目录，只读挂载；Windows 可用 `D:/datasets` |

- 源目录在界面显示为 `~/imports`；不是宿主原绝对路径。目录需允许 UID/GID 10001 读取，Docker Desktop 还需允许目录共享。导入后由应用物化到受管工作区，TXT 标注入数据库。来源挂载与命名卷通常不在同一文件系统，reflink/hardlink 不可用时回退 copy，不能保证零复制。
- 后端以非 root 用户 10001:10001 运行。共享 `home` 命名卷位于 `/data/home`，同时保存 home 定位文件、工作区、数据库、媒体、模型、输出和凭据密钥；必须整体持久化/备份，不能只挂载数据库目录。
- 两个版本默认使用相同 Compose 项目名和卷。切换前先完成/取消所有排队及活动任务，停止整个栈并备份卷，再使用另一组文件启动。CPU 保留旧模型、历史评估及推理、engine 下载，不执行本地模型任务；恢复 GPU 后重新检查 engine 环境指纹。
- API、Worker、web 必须使用同一版本代码。当前只支持一个 API 和一个 Worker，不能 `--scale` 扩容。`docker compose stop` 保留数据；**不要对需保留数据的实例执行 `down -v`**。
- Nginx 保留原 Host（含端口），支持 SPA 深链接、流式 API/SSE，API 缓冲关闭。只开放 web 端口；当前为 HTTP 同源部署，API 禁用可信代理头。外部 TLS 终止未验收，不能直接依赖 `X-Forwarded-*` 绕过同源边界。
- 单请求上限 1 GB，反向代理超时 600 秒。测试集 ZIP 解压上限 5 GB；需为媒体、模型、训练输出及临时目录预留磁盘空间。

## 构建、离线分发与更新

Dockerfile 使用 Python 3.12 slim、uv 0.11.7 冻结锁文件、Node 22/npm ci、Nginx 1.28。CPU/GPU/web 是独立 target；CPU 运行镜像不含 uv、开发工具或 GPU extra。`.dockerignore` 采用源代码白名单，排除 `.ai-local`、`.env`、依赖目录和业务数据；不要将真实密钥写为 build-arg。

GPU 首次构建下载量和磁盘占用较大。实测镜像未压缩约 CPU 676 MB、web 66 MB、GPU 13.8 GB；构建缓存还需额外空间。基础镜像 tag 与冻结 Python/npm 锁文件不等同完整系统包永久复现，发布时应保存镜像摘要/归档并按组织流程扫描。

若目标主机 registry mirror 不可用，可在同一目标架构机器构建后离线加载：

```bash
docker save vision-dataset-workbench:cpu vision-dataset-workbench:web -o vdw-cpu.tar
# 将镜像归档及 compose 文件传到目标主机
docker load -i vdw-cpu.tar
docker compose up -d --no-build
```

GPU 分发时保存 `vision-dataset-workbench:gpu` 和 `:web` 并使用 GPU override。本轮 Windows 原生构建被已有镜像源 403 阻断，通过此加载方式部署并完成业务/持久性验证；未更改其全局镜像源。macOS 和 Linux 已完成本机构建。镜像尚未推送公共仓库。

更新前停止任务并备份完整卷，然后 `docker compose stop`、构建/加载新镜像、`up -d --wait`。GPU 实例所有命令均携带 `-f compose.yaml -f compose.gpu.yaml`。API 在启动已有工作区时执行迁移，Worker 等待 API 健康后启动；不兼容 schema 回滚需恢复备份。实际验收范围见[测试策略](06-testing-strategy.md)。

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
- 登录要求用户名和密码，不提供无认证入口。
- 当前认证使用数据库可撤销 Session，部署时不需要共享浏览器 Token；不得记录 `vdw_session` Cookie 或数据库中的 token 摘要。
- 当前同源校验直接使用请求 scheme 与 Host，不支持可信代理头。引入 TLS 终止代理前必须先明确并测试代理边界。
- `YTDLP_PROXY` 可配置实例级代理，`YTDLP_COOKIE_FILE` 可指向 Netscape Cookie 文件；二者可能包含敏感信息，不得写入日志或仓库。
- 生产远程下载采用一个由运维维护的共享下载账号。运维人员在主机上的专用浏览器配置中交互登录目标站点，确认登录有效后导出 Netscape `cookies.txt`；普通业务用户不上传 Cookie，服务也不内置无界面浏览器或映射日常浏览器配置目录。Cookie 到期时重复登录、导出和替换流程。
- 原生部署把 Cookie 文件放在仓库与工作区之外，权限设为 `0600`，并让 API 与 Worker 的 `YTDLP_COOKIE_FILE` 指向同一只读文件。Docker 部署应把它作为 Secret 或只读单文件挂载同时注入 API 与 Worker，例如容器内 `/run/secrets/vdw_ytdlp_cookies`；不得挂载整个浏览器配置目录。固定 `YTDLP_PROXY` 可保持下载出口稳定；显式 User-Agent 注入尚未实现，遇到站点绑定 User-Agent 时必须先用实际 yt-dlp 链路验证，不能假定仅有 Cookie 即可长期工作。
- 运维流程以 [yt-dlp Cookie FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp) 和 [Docker Compose Secrets](https://docs.docker.com/compose/how-tos/use-secrets/) 为准；Cookie 文件按凭据管理和轮换，不进入普通配置备份、日志或问题截图。
- 用户配置的 X-AnyLabeling Server 和在线大模型 API 密钥均使用工作区 Fernet 密钥加密后写入数据库。未设置 `VDW_CREDENTIAL_ENCRYPTION_KEY` 时，应用原子生成并复用 `<workspace>/config/credential.key`；应随工作区备份该权限为 `0600` 的文件，API 与 Worker 必须挂载同一工作区。也可显式设置环境变量覆盖自动密钥。
- 在线大模型客户端继承标准 `HTTP_PROXY`、`HTTPS_PROXY` 和 `ALL_PROXY`；后端基础依赖包含 HTTPX SOCKS 支持，因此 `socks5://` 代理不需要额外安装。部署冒烟应分别发送最小文本请求和合成图片请求，且不得打印解密后的连接配置或 API Key。
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

## 0029 图像项目升级

API 启动会执行 Alembic 升级；升级前停止旧 API/Worker 并备份完整工作区，再以同一版本启动 API、Worker、前端。迁移新增 import_images 约束和图片四表，旧 Worker 不可处理新任务。基础依赖现已包含 Pillow，纯图/YOLO 导入不要求 gpu extra。本轮已在隔离的 0028 历史 fixture 上演练升级，未对真实工作区执行升级；部署前仍需备份并在工作区副本演练。存在图片项目/导入或相关任务历史时迁移拒绝降级，应使用升级前备份回退。

## 健康与可观测性

- `GET /api/v1/health` 当前只返回进程存活；Compose API/web healthcheck 使用它，不代表数据库、初始化或 GPU 就绪。初始化状态另查 `/api/v1/setup/status`，GPU 能力另查 `/api/v1/capabilities`。
- Worker 活动任务在 SQLite 中持久化租约/心跳；暂无独立空闲 Worker readiness/health HTTP 端点，需结合容器状态和任务进展检查。
- 日志包含时间、级别、服务、请求/任务 ID 和项目 ID，不记录 Cookie、Token、完整代理 URL 或用户文件内容。
- 尚未提供独立指标采集栈；生产需按任务失败、租约、磁盘和进程状态配置监控。
- 长任务日志和最终错误需可由任务 ID 查询。
- 监控转换产物、临时推理会话、保存结果和评估集占用；未保存推理会话按 24 小时访问超时由后台清理，保存结果只由用户显式删除。

## 备份与回滚

- 备份范围包含数据库、项目元数据、标注、媒体、模型、配置与凭据密钥；容器部署停止栈后备份整个 `home` 卷（含定位文件），不要只复制 SQLite 主文件。
- 停止 API 和 Worker 后，可整体复制 `.vision-dataset-workbench` 备份数据库、配置、媒体、标注、模型和任务记录。
- 在线备份不能只复制 SQLite 主文件；实现后需使用 SQLite backup API 或先执行安全 checkpoint。
- 应用回滚前确认旧版本能读取迁移后 schema；不能兼容时使用预先验证的数据恢复流程。
- 回滚不得简单删除正在运行任务的输出目录；先停止领取并核对任务租约。

恢复时间目标、恢复点目标和数据保留周期：`Unknown`，需由部署所有者确认。
