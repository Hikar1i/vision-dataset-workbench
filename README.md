# Vision Dataset Workbench

面向目标检测的视觉数据集与模型工作台，覆盖 **数据导入 → 筛选 → 标注 → 数据集导出 → 训练 → 推理与评估**。支持视频采样帧、纯图像目录和 YOLO Detect 数据集，提供多人协作与 CPU / NVIDIA GPU 两种容器部署方式。

技术栈：Vue 3 · TypeScript · FastAPI · Python 3.12 · SQLite · Ultralytics YOLO · FFmpeg。

[功能概览](#功能概览) · [容器部署](#容器部署) · [本地开发](#本地开发) · [首次使用](#首次使用) · [运行维护](#运行维护) · [常见问题](#常见问题) · [项目文档](#项目文档)

## 功能概览

| 模块 | 功能 |
| --- | --- |
| 视频数据集 | 本地视频及远程链接导入、内容去重、采样方案、抽帧、筛帧与启停管理 |
| 图像数据集 | 纯图像 / YOLO Detect 目录导入、目录筛选、重复导入只补新图、缩略图网格与全屏预览 |
| 标注工作台 | 矩形框绘制与编辑、类别管理、快捷键、缩放与切图、标注修订冲突检测 |
| 自动标注 | 本地 YOLO、外部 X-AnyLabeling Server、OpenAI-compatible / Anthropic 在线视觉模型 |
| 数据集导出 | 导出 YOLO 数据集快照、目录级训练/验证分配、统一或独立比例、正负样本分别划分 |
| 模型与训练 | YOLO `.pt` 模型入库、超参数模板、单/多数据集训练、GPU 队列、训练曲线及模型产物管理 |
| 推理与评估 | 图片/视频在线推理、保存结果、测试集评估、ONNX / TensorRT 转换与下载 |
| 团队协作 | 管理员创建账号、项目成员与 owner/editor/viewer 权限、持久任务与失败记录 |

当前任务范围为**轴对齐矩形框目标检测**，不支持分割、多边形、姿态或旋转框数据集。

## 选择运行方式

| 方式 | 适用场景 | 前提 |
| --- | --- | --- |
| CPU 容器 | 无 GPU、AMD / Intel 显卡、数据集整理与标注 | Docker Engine + Compose v2，或 Docker Desktop 的 Linux containers |
| GPU 容器 | 本地自动标注、训练、推理、评估及格式转换 | 兼容的 NVIDIA GPU、驱动和容器 GPU 支持 |
| 本地开发 | 修改前后端源码、调试 API / Worker | Python 3.12、uv、Node.js、FFmpeg / ffprobe |

CPU 版可导入、筛选、手工/远程标注、导出数据集、管理模型和测试集、查看与下载历史结果；**不执行本地模型自动标注、训练、转换、在线推理或评估**。远程标注需要自行配置可达的外部服务。

容器 CPU 部署已在 Ubuntu 22.04、Windows 11 Docker Desktop、Intel macOS 15 Docker Desktop 的 Linux/amd64 环境验证；GPU 完整短流程已在 Linux NVIDIA 主机验证。ARM64 尚未验收；macOS Docker Desktop 下的 AMD 显卡使用 CPU 配置。

## 容器部署

### 1. 准备 Docker 和完整源码

安装并启动 Docker 和 Docker Compose 在终端确认：

```bash
docker version
docker compose version
```

获取项目并进入仓库根目录：

```bash
git clone https://github.com/Hikar1i/vision-dataset-workbench.git
cd vision-dataset-workbench
```

请使用包含容器部署文件的版本。构建需要完整源码，目录至少包含：

```text
vision-dataset-workbench/
├── Dockerfile
├── compose.yaml
├── compose.gpu.yaml
├── .env.example
├── .dockerignore
├── deploy/
├── backend/                 # 包含 pyproject.toml、uv.lock、src 和 Alembic 迁移
└── frontend/                # 包含 package.json、package-lock.json 和前端源码
```

仓库使用的文件名是 `compose.yaml`，Docker Compose 会自动发现它，无需改名为 `docker-compose.yml`。**只有 Compose 文件不足以构建镜像**。构建需要访问基础镜像仓库、Python 和 npm 依赖源；离线部署见下文。

### 2. 准备导入目录与配置

Linux / macOS：

```bash
cp .env.example .env
mkdir -p imports
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force imports
```

把待导入的图像、YOLO 数据集、视频或 `.pt` 模型放入 `imports/`，或在 `.env` 中指定已有目录：

```dotenv
VDW_BIND_ADDRESS=127.0.0.1
VDW_PORT=8080
VDW_IMPORTS=./imports
```

| 配置 | 说明 |
| --- | --- |
| `VDW_BIND_ADDRESS` | `127.0.0.1` 仅部署主机本机可访问；通过局域网访问时改为 `0.0.0.0`，并允许主机防火墙对应端口 |
| `VDW_PORT` | Web 访问端口，默认 `8080`；冲突时改为其他空闲端口 |
| `VDW_IMPORTS` | 宿主机来源目录，相对路径以 Compose 文件所在目录为基准；Windows 可写 `D:/datasets`，带空格时用引号包裹值 |

容器内来源目录固定为 **`~/imports`（`/data/home/imports`）**，界面中应从这里选择文件，而不是填写宿主机的绝对路径。来源为只读挂载；Linux 目录须允许容器 UID/GID `10001:10001` 读取，Docker Desktop 须允许该目录共享。

### 3. 构建镜像并启动服务

以下两组命令选择一组执行。

#### CPU 版

```bash
# 构建 CPU 后端和 Web 镜像
docker compose build api web

# 启动 API、Worker、Web，等待已配置的健康检查通过
docker compose up -d --no-build --wait

# 查看状态与首次初始化口令
docker compose ps
docker compose logs api
```

也可一步完成构建和启动：`docker compose up -d --build --wait`。

#### NVIDIA GPU 版

Linux 需安装 NVIDIA 驱动并配置 NVIDIA Container Toolkit；Windows 需具备受支持的 NVIDIA GPU 和 WSL2 Docker Desktop GPU 环境。当前完整 TensorRT 依赖要求兼容的 **R580 或更新驱动**；具体前提见[GPU 部署说明](project-docs/07-deployment.md#nvidia-gpu-部署)。无需在宿主机额外安装 CUDA Toolkit。

```bash
docker compose -f compose.yaml -f compose.gpu.yaml build api web
docker compose -f compose.yaml -f compose.gpu.yaml up -d --no-build --wait
docker compose -f compose.yaml -f compose.gpu.yaml ps
docker compose -f compose.yaml -f compose.gpu.yaml logs api
```

GPU 版后续的日志、停止、重启、更新及管理命令也必须携带 **`-f compose.yaml -f compose.gpu.yaml`**，以保持 API / Worker 使用相同镜像和 GPU 设备视图。

构建产物为 `vision-dataset-workbench:cpu` 或 `:gpu`，以及 `:web`；API 和 Worker 共用后端镜像。镜像在本机构建，不依赖已发布的项目镜像仓库。GPU 镜像约 13.8 GB，首次下载与构建需预留额外磁盘和缓存空间。

### 4. 浏览器初始化并登录

1. 默认在部署主机打开 `http://127.0.0.1:8080`。若已配置 `VDW_BIND_ADDRESS=0.0.0.0`，用户打开 `http://部署主机IP:8080`；端口与 `.env` 一致。`0.0.0.0` 是监听地址，不是浏览器访问地址。
2. 从 API 日志找到 `Vision Dataset Workbench setup token: ...`，把口令填入首次初始化向导。
3. 选择工作区父目录。容器部署可选择 home 根目录 `/data/home`，应用会创建 `/data/home/.vision-dataset-workbench`；**不要选择只读的 `imports` 目录**。
4. 自行设置首个管理员的用户名和密码（密码长度 12–256 个字符），完成初始化后登录。
5. 管理员可创建其他用户账号；普通账号使用生成的初始密码登录后，先设置自己的密码。系统不开放自行注册。

**镜像没有默认用户名或密码。** `setup token` 只用于首次初始化，成功后立即失效；已有工作区重启后直接登录，不重复初始化。容器 Worker 会等待初始化完成，再自动开始领取任务。

### 5. 确认服务可用

```bash
docker compose ps
docker compose logs --tail 100 api worker web
```

浏览器访问 `http://127.0.0.1:8080/api/v1/health` 应得到 `{"status":"ok"}`；`/api/v1/setup/status` 可查看是否已初始化。健康检查只表示 API 进程可响应，不代表 GPU 或任务调度已就绪。

登录后确认项目可创建、导入任务能完成；GPU 版还应在界面检查运行能力及 GPU 状态。只有依赖安装成功，不代表硬件运行能力已通过检测。

### 离线部署：构建一次，在同架构主机加载

在可联网的构建主机执行 CPU 构建，然后保存镜像：

```bash
docker compose build api web
docker save -o vdw-cpu.tar vision-dataset-workbench:cpu vision-dataset-workbench:web
```

将归档、`compose.yaml`、`.env.example` 传到目标主机，按前文创建 `.env` 和导入目录，再运行：

```bash
docker load -i vdw-cpu.tar
docker compose up -d --no-build --wait
docker compose logs api
```

GPU 版保存 `:gpu` 和 `:web`，同时分发 `compose.gpu.yaml`，启动时使用两份配置。目标主机应与构建镜像使用相同架构，并满足相应 GPU 前提。该方式不需要源码或 Dockerfile；**不要省略 `--no-build`**。

## 本地开发

### 1. 环境要求

| 工具 | 要求 |
| --- | --- |
| Git | 获取项目源码 |
| Python | `3.12.x`，项目约束为 `>=3.12,<3.13`，可由 uv 安装 |
| uv | 安装后端依赖并运行 API / Worker |
| Node.js / npm | 建议 Node.js 22（至少 `22.13`）及其配套 npm |
| FFmpeg / ffprobe | 视频探测、缩略图和抽帧；两个命令都需加入 PATH |
| NVIDIA 环境 | 仅本地模型功能需要；CPU 开发无需安装 GPU extra |

先安装以上工具，再检查 `uv --version`、`node --version`、`npm --version`、`ffmpeg -version`、`ffprobe -version`。Ubuntu / Debian 可通过 `sudo apt-get install ffmpeg` 安装视频工具，macOS 可使用 `brew install ffmpeg`；Windows 安装后将其可执行文件目录加入 PATH。

从仓库根目录准备依赖：

```bash
# uv 可安装所需 Python；不会替换系统 Python
uv python install 3.12
cd backend
uv sync --python 3.12 --frozen --dev
```

需要在受支持的 NVIDIA 环境开发本地模型功能时，最后一行改为：

```bash
uv sync --python 3.12 --frozen --dev --extra gpu
```

另一个终端从仓库根目录安装前端依赖：

```bash
cd frontend
npm ci
```

后续 `uv run --no-sync` 复用已安装的环境，保留上一步选定的 CPU / GPU 依赖。修改依赖后需重新执行对应的 `uv sync`。

### 2. 启动 API

在第一个终端，从仓库根目录执行：

```bash
cd backend
uv run --no-sync uvicorn vision_dataset_workbench.main:app --app-dir src --reload --host 127.0.0.1 --port 38000
```

保留该终端；首次启动时记下打印的 `setup token`。如果已配置可用工作区，应用直接加载工作区并执行必要的数据库迁移。

### 3. 启动前端并完成初始化

在第二个终端，从仓库根目录执行：

```bash
cd frontend
npm run dev
```

打开 `http://127.0.0.1:35173`，使用 API 终端中的初始化口令，在**启动用户 home 范围内**选择工作区父目录并创建管理员。已初始化实例直接登录。

前端通过 Vite 将 `/api` 同源代理到 `http://127.0.0.1:38000`。前端端口固定为 `35173`，占用时直接报错；请通过前端地址使用系统。

### 4. 初始化后启动 Worker

在第三个终端，从仓库根目录执行：

```bash
cd backend
uv run --no-sync python -m vision_dataset_workbench.worker
```

原生 Worker 在未初始化时会退出，因此首次开发启动应先完成上一步；以后可在 API 启动后直接启动 Worker。API 和 Worker 必须使用同一系统用户、Python 环境、工作区配置及版本。只启动前端/API，不会自动执行后台导入、抽帧或训练任务。

### 5. 日常调试与停止

- 三个终端分别按 `Ctrl+C` 停止服务，数据保留在工作区。
- API 的 `--reload` 不会重载独立 Worker；修改任务执行或调度代码后，等待活动任务结束并重启 Worker。
- 本地开发默认只供本机访问。需要局域网访问前端时使用 `npm run dev -- --host 0.0.0.0`，通过开发主机 IP 的 `35173` 端口访问；Vite 仍代理同机 API。开发服务器不用于长期部署。
- `VDW_WORKSPACE` 可指定 home 范围内的已有工作区，API / Worker 两个终端需设置为同一路径；完整配置见[环境与启动](project-docs/08-environments.md)。仓库根 `.env` 是 Compose 的变量文件，原生开发命令不会自动读取它。

可按需执行开发检查：

```bash
# 后端目录
uv run --no-sync pytest
uv run --no-sync ruff check src tests alembic

# 前端目录
npm test
npm run build
```

## 首次使用

1. **创建数据集项目**：选择视频或图像类型。
2. **导入数据**：视频配置采样并抽帧；图像选择纯图目录或 YOLO Detect 数据集。YOLO 的 `train/valid/test` 导入后仅作为来源目录保留，不固定其训练角色。
3. **筛选与标注**：停用不参与导出的图片/帧，手工标注或配置自动标注来源。本地模型需先把自己的 YOLO `.pt` 文件导入模型项目；内置模型项目不代表预装了模型权重。
4. **导出数据集**：为图像目录指定训练/验证或比例划分，创建数据集快照。无框图片会作为负样本，含目标但未完成标注的图片应先补标或排除。
5. **训练与验证**：GPU 实例中选择已导出的单个或多个数据集、基础模型与超参数模板，再创建训练任务；之后在模型项目中使用推理、格式转换与评估功能。

评估测试集 ZIP 使用以下结构，负样本保留同名空 TXT：

```text
helmet-testset.zip
├── classes.txt
├── images/
│   ├── sample.jpg
│   └── negative.jpg
└── labels/
    ├── sample.txt
    └── negative.txt
```

容器中访问外部标注服务时，`127.0.0.1` 指容器自身；地址须能同时被 API 和 Worker 访问。Docker Desktop 访问宿主服务可使用 `host.docker.internal`。在线视觉模型需要自己的服务地址、模型名和 API Key。

## 运行维护

### 停止、重启与更新

以下为 CPU 示例；GPU 实例所有命令增加两份 `-f` 参数，使用独立项目名的实例还应保持同一 `-p 项目名`。

```bash
# 停止服务，保留容器和数据卷
docker compose stop

# 恢复服务
docker compose up -d --no-build --wait
```

更新前先完成或取消所有排队/活动任务，停止服务并备份完整数据卷，再更新源码、构建镜像和启动：

```bash
docker compose stop
# 在此备份数据卷，再更新源码
git pull
docker compose build api web
docker compose up -d --no-build --wait
```

API 启动已有工作区时自动升级 schema。回滚前确认数据库兼容性，不能兼容时恢复升级前备份。切换 CPU / GPU 使用同一数据卷，也须先结束任务、停止整套服务并备份。

### 数据保存在哪里

| 内容 | 容器位置 / 行为 |
| --- | --- |
| 导入来源 | `/data/home/imports`，宿主目录只读挂载 |
| 持久化根 | `/data/home`，Compose 的 `home` 命名卷 |
| 默认示例工作区 | `/data/home/.vision-dataset-workbench`，实际位置由初始化时选择的父目录决定 |
| 数据库、媒体与模型 | 工作区内保存，重建镜像不会清空 |
| 账号与密码 | 用户与密码哈希保存在工作区数据库，不在镜像中 |
| 远程服务凭据密钥 | 自动生成于工作区 `config/credential.key`，应连同工作区备份 |

实际卷名带 Compose 项目前缀，可用 `docker volume ls` 查看。命名卷由 Docker 管理，在 Docker Desktop 中不等同宿主某个同名目录。完整备份应包含 home 内的定位文件、数据库、媒体、模型与密钥；执行备份前停止 API 和 Worker。

**不要对需要保留数据的实例执行 `docker compose down -v`**，它会删除数据卷。不要通过更换 `-p` 项目名寻找旧数据：不同项目名通常会创建另一套卷，使页面看起来像全新实例。

### 忘记管理员密码

系统不提供查看原密码功能。普通用户由管理员在账号管理中重置；管理员使用离线命令交互式重置，新密码不会作为命令参数传入。

容器示例（假设初始化时选择 `/data/home`，管理员用户名为 `admin`；请替换为实际值）：

```bash
docker compose stop
docker compose run --rm --no-deps api python -m vision_dataset_workbench.admin reset-password --workspace /data/home/.vision-dataset-workbench --username admin
docker compose up -d --no-build --wait
```

命令会提示输入并确认新密码。GPU 实例使用相同 GPU 配置和项目名。若忘记工作区路径，可在停止后查看定位文件中的 `workspace`：

```bash
docker compose run --rm --no-deps api cat /data/home/.config/vision-dataset-workbench/instance.json
```

原生开发：停止 API / Worker，在 `backend/` 执行下列命令，完成后重新启动：

```bash
uv run --no-sync python -m vision_dataset_workbench.admin reset-password --workspace /absolute/path/.vision-dataset-workbench --username admin
```

## 常见问题

| 现象 | 排查方法 |
| --- | --- |
| 无法通过 IP 访问容器 | 检查 `VDW_BIND_ADDRESS=0.0.0.0`、端口、防火墙及主机可达性；修改 `.env` 后运行对应配置的 `up -d`，仅 `restart` 不会应用端口变更 |
| 找不到初始化口令 | 查看当前 API 日志；未初始化实例重启 API 会生成新口令，旧日志中的口令不能继续使用；已初始化实例直接登录 |
| 登录密码在哪里 | 新实例由首次管理员自行设置，没有默认密码；日志只含初始化口令，数据库只存密码哈希，忘记后按前文重置 |
| 页面正常但导入/抽帧一直排队 | 检查 Worker 是否运行、初始化是否完成，以及 API / Worker 是否指向相同工作区 |
| 容器中看不到宿主文件 | 检查 `VDW_IMPORTS` 和 Docker Desktop 目录共享；界面从 `~/imports` 选择，检查容器用户读取权限 |
| 显示 CPU 降级或 GPU 功能禁用 | CPU 版为预期行为；GPU 版检查两份 Compose 配置、驱动、容器设备及运行能力原因，不要只看镜像构建是否成功 |
| Docker 拉取或构建返回 403 / 超时 | 先区分镜像拉取与构建容器内 apt/uv/npm 下载；apt 超时可在 `.env` 设置 `VDW_DEBIAN_MIRROR` 后重建，详见[构建网络排查](project-docs/07-deployment.md#构建容器无法访问-debian-源)。也可离线加载完整应用镜像 |
| 更新后像全新实例 | 检查是否换了 Compose 项目名、数据卷，或原生启动用户 / `VDW_WORKSPACE`；先定位原工作区，不要覆盖旧数据 |
| TensorRT 引擎换机器不可用 | `.engine` 与构建硬件/运行时绑定，在目标 GPU 环境重新转换；不要把它当作通用模型格式 |

系统当前按单机部署设计，使用本地 SQLite、单 API 和单 Worker，不支持横向扩容或网络盘上的共享 SQLite。HTTP 同源部署已验证；外部 HTTPS/TLS 终止需要额外验证代理和认证边界。更多排查见[已知问题](project-docs/09-known-issues.md)。

## 项目文档

- [部署与运维](project-docs/07-deployment.md)：GPU 前提、网络、持久化、备份和升级。
- [开发环境与配置](project-docs/08-environments.md)：工作区定位、账号认证、远程服务与依赖。
- [系统架构](project-docs/02-architecture.md) · [数据库与迁移](project-docs/03-database.md) · [API](project-docs/04-api.md)。
- [测试策略](project-docs/06-testing-strategy.md) · [代码规范](project-docs/05-code-style.md) · [UI/UX 设计系统](project-docs/10-ui-ux-design-system.md)。
- [项目背景](project-docs/01-project-background.md) · [已知问题](project-docs/09-known-issues.md)。

## Agent 辅助部署

将完整项目交给目标机器上的 AI Agent，在项目目录中输入以下提示词即可：

```text
当前项目是 Vision Dataset Workbench（VDW）。请阅读并按照 deploy/agent-deployment.md 的流程，在当前机器完成 Docker 部署；检测环境后自动选择 CPU 或 NVIDIA GPU，完成管理员初始化、实际登录和运行验收，并交付访问地址、登录凭据及启停方式。已有实例请保留数据，遇到必须由我提供的信息或授权时再询问。
```

[Agent 部署流程](deploy/agent-deployment.md) 包含环境检测、CPU/GPU 选择、构建或离线加载、旧实例保护、初始化和验收步骤。完整步骤保存在文档中，用户无需复制长提示词。

通过 Git 获取项目即可使用上述流程。需要交付精简源码包时，可选用 [源码打包附件](deploy/package_source.py)，具体用途、文件约束和离线镜像准备见流程文档附录；该附件不是目标机部署的前置依赖。
