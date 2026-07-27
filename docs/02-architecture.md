# 架构

状态：总体设计已批准，初始化、认证、项目权限、视频导入、采样、抽帧、筛帧、项目标签、在线矩形标注、模型入库和自动标注已实现。

## 当前仓库状态

当前仓库已有 Vue/FastAPI 初始化链路、账号与项目权限、十版 SQLite 迁移、安全路径组件、媒体、帧、项目标签、矩形标注、模型推理、GPU 能力探测和独立 Worker。训练和导出仍是目标设计。因此本页区分：

- 遗留架构：已经从 `dataset-manager-1` 代码验证的现状，仅作为重构输入。
- 当前基础：已经实现并验证的初始化链路。
- 目标设计：已经批准但尚未全部实现的职责划分和技术基线。

## 当前应用基础

```text
Vue setup/auth/admin/project/media pages
  ├─ /api/v1/setup/* → SetupService → HomePathResolver / WorkspaceLocator
  ├─ /api/v1/auth + registrations + admin/users → AuthService
  │    ├─ Argon2 password verification
  │    ├─ SHA-256 token digest + SQLite sessions
  │    └─ User registration/status transitions
  ├─ /api/v1/projects + members → ProjectService
  │    ├─ private project visibility + role checks
  │    └─ optimistic version updates
  ├─ /api/v1/projects/<id>/labels → LabelService
  │    ├─ project-scoped English classes + stable UUID
  │    └─ owner/editor writes + viewer reads
  ├─ /api/v1/capabilities → startup-cached capability probe
  │    ├─ nvidia-smi device inventory
  │    └─ PyTorch CUDA / ONNX CUDA / Ultralytics / Transformers readiness
  ├─ /api/v1/filesystem → HomePathResolver
  ├─ /api/v1/projects/<id>/videos|imports|tasks → MediaService
       ├─ SQLite Video / Task state
       ├─ authenticated playback, Range and download
       └─ workspace/projects/<project UUID>
  ├─ /api/v1/projects/<id>/sampling-plans|extractions|frames → SamplingService
       ├─ predictable sampling calculation + plan versioning
       ├─ stable Frame records + revision-protected filtering
       └─ authenticated frame image delivery
  ├─ /api/v1/.../frames/<id>/annotations → AnnotationService
  │    └─ original-pixel rectangles + annotation revision
  └─ /api/v1/models|auto-annotations → ModelService / AutoAnnotationService
       ├─ synchronous single-frame review draft
       └─ persistent batch task creation

Independent Python Worker
  ├─ SQLite lease / progress / cancel / retry
  ├─ local copy + SHA-256 + ffprobe + FFmpeg thumbnail
  ├─ yt-dlp HTTP(S) download + remote identity deduplication
  ├─ FFmpeg frame extraction + atomic generation replacement
  ├─ inference model copy + atomic publication
  └─ per-frame batch auto annotation + progress/status publication
```

API 请求负责校验、权限和应用服务编排。视频导入、抽帧、模型入库和批量自动标注只创建持久任务并立即返回；复制、下载、媒体探测、抽帧、模型复制和批量推理在独立 Worker 中执行。单张自动标注是为交互复核保留的例外：在 API 同步线程池中运行并只返回草稿，不直接改写标注。帧文件和模型先写任务临时目录，验证后原子发布。审计表、训练和导出尚未实现。

## 遗留架构基线

```text
Vue 3 SPA
  ├─ ProjectSelector.vue
  └─ DatasetManager.vue
          │ HTTP + SSE
          ▼
Flask app.py
  ├─ 路由、SQL、运行时迁移
  ├─ 状态流转与文件编排
  ├─ daemon threads + 内存队列
  ├─ FFmpeg / ffprobe
  └─ VideoManager → yt-dlp
          │
          ├─ 管理 SQLite
          └─ 每项目 SQLite + 项目文件目录
```

遗留前端以两个超大页面组件承载界面、API、并发调度和业务状态。后端除 yt-dlp 封装外，几乎全部集中在约 4500 行的 `app.py`。任务和 SSE 订阅只存在于单进程内存；数据库与文件系统跨阶段更新；没有认证授权。该结构不得作为新项目模块组织模板。

## 当前与已批准的扩展架构

```text
Vue 3 + TypeScript Client
  ├─ 页面与工作区布局
  ├─ 按领域拆分的 UI 状态
  └─ OpenAPI 契约 Client
              │ HTTP + 任务事件
              ▼
FastAPI Application
  ├─ 初始化、身份、注册审批与项目权限
  ├─ 请求校验与响应映射
  └─ 应用服务编排
       ├─ Project / Video / Frame / Annotation / InferenceModel / Export
       ├─ SQLAlchemy services（当前）
       ├─ Storage Gateway
       └─ Task Gateway
              │
      ┌───────┴────────┐
      ▼                ▼
SQLite             Persistent Worker
                       ├─ yt-dlp
                       ├─ FFmpeg / ffprobe
                       ├─ 模型入库与批量自动标注
                       └─ 数据集导出
              │
              ▼
       Controlled Storage Root
```

### 前端职责

- 路由页面只组织用户流程，不直接实现业务算法。
- 项目、媒体、帧、标注、模型、任务和导出使用独立的功能模块。
- 服务端状态是任务与资源的事实来源；页面本地状态只保存交互状态和可丢弃缓存。
- 批量操作提交服务端任务，不在浏览器中制造 O(视频数 × 帧数) 的请求瀑布。
- UI 追求高信息密度、清晰层级和键鼠高效操作，具体设计系统在前端实现前确认。

### API 应用职责

- 校验输入、认证上下文和资源权限。
- 把 HTTP 契约映射到应用服务，不直接包含 SQL、FFmpeg 或文件复制细节。
- 所有状态转移调用同一领域规则，查询不得隐式迁移 schema 或修复业务状态。
- 对跨数据库与文件系统的操作创建 SQLite 持久任务，并暴露明确的部分失败状态。

### 领域职责

- 定义视频工作流状态、合法转移和导出资格。
- 把采样估算、train/val 划分等算法实现为无 I/O 的可测试函数。
- 区分持久资源状态与任务运行状态，避免把 `DOWNLOADING` 等瞬时进度写入视频生命周期。
- 不依赖具体 Web 框架、ORM、任务队列或文件系统实现。

### 基础设施职责

- Repository：持久化领域数据，迁移只通过版本化迁移工具执行。
- Task Worker：独立于 API，领取有租约的 SQLite 任务，记录心跳、进度、重试和最终结果。
- Storage Gateway：所有路径都相对配置的存储根解析，拒绝逃逸和任意绝对路径。
- Media Adapters：隔离 yt-dlp、FFmpeg、ffprobe 的命令构造、超时和错误映射。

## 状态与任务模型

当前已实现的视频生命周期为：

`pending` → `ready`

复制或下载失败记录在 Task，视频保留为 `pending` 供重试；文件确实不可用时预留 `unavailable`。采样不再改变视频生命周期：每个视频最多一个 SamplingPlan；方案版本未应用为 `configured`，当前版本已抽出帧为 `sampled`。帧启停保存于稳定 Frame 记录，并用 `frame_revision` 防止并发覆盖。

任务状态与业务状态分离。复制、下载、抽帧、模型入库和批量自动标注使用 queued、running、succeeded、failed、canceled；任务记录包含类型、提交者、资源范围、进度、尝试次数、错误、取消标记、租约和时间。批量自动标注要求视频启用，并按 Worker 开始执行时启用的帧集合逐帧提交；失败或取消时保留已成功帧。导出后续复用该状态模型。

## 一致性原则

- 数据库是资源元数据和任务状态的事实来源；文件存在本身不自动代表业务完成。
- 文件输出先写临时位置，验证后原子发布；任务重试不得重复破坏已完成结果。
- 跨资源事务无法原子完成时，记录执行阶段并提供补偿或安全重试。
- 事件从持久任务状态派生；进程重启和多 Worker 不得丢失最终状态。

## 运行与存储边界

- 默认多用户；可通过配置切换为仅初始化管理员可登录的单用户账号密码模式。
- 浏览器会话只把随机原始值放入 HttpOnly Cookie，SQLite 只保存 SHA-256 摘要；12 小时空闲过期、7 天绝对过期，访问触达最多每 5 分钟写库一次。
- 所有浏览器写请求要求 `Origin` 与当前请求 origin 完全一致；当前不提供跨域认证、IP 规则或可信代理模式。
- 所有模式共用用户、权限和数据，单用户模式临时以工作区管理员访问全部项目。
- 所有受管理数据位于 `<parent>/.vision-dataset-workbench/`。
- 所有认证用户可浏览启动用户 `~`，导入后复制到工作区；API 不暴露绝对路径。
- Worker 与 API 读取同一 SQLite 和工作区。复制、下载和抽帧各自全局并发 2、同类型每用户并发 1；每个 FFmpeg 抽帧进程限制 2 个线程，当前只部署一个调度 Worker。
- 项目媒体位于 `projects/<project UUID>/videos/`，缩略图位于 `projects/<project UUID>/thumbnails/`，采样帧位于 `projects/<project UUID>/frames/<video UUID>/`；执行中输出位于顶层 `tmp/<task UUID>/`，验证后原子发布。
- Linux 原生使用 systemd，Windows 使用进程启动器，同时支持 Docker Compose。
- Docker 未提供 GPU 时正常启动并禁用训练/自动标注。
- Python 核心依赖不包含模型运行库；GPU 服务器通过 uv 的 `gpu` extra 安装 CUDA 12.8 PyTorch、Ultralytics、Transformers 和 ONNX Runtime GPU。
- 只支持单机本地磁盘，不支持跨服务器 Worker 或网络文件系统上的 SQLite。

当前及后续工作区目录约定：

```text
projects/<project UUID>/
├─ videos/                         # 已实现：受管原始视频
├─ thumbnails/                     # 已实现：视频缩略图
├─ frames/<video UUID>/            # 已实现：当前一代规范采样帧
├─ labels/<video UUID>/            # 计划：导出前的规范标签文件；在线标注当前存入 SQLite
├─ annotation-batches/<batch UUID>/ # 逻辑概念：当前批量任务直接按 Frame 记录处理，不物化固定分组目录
└─ exports/<export UUID>/           # 计划：不可变数据集导出

models/<model UUID>/                # 已实现：受管推理模型文件或 Transformers 目录
```

遗留 `thumbnails/` 对应新的项目级 `thumbnails/`；遗留 `dataset/` 对应后续 `exports/<export UUID>/`；遗留 `groups/` 不作为普通数据目录照搬，而对应后续自动标注任务的帧快照/分片概念。新系统直接调用 YOLO、GroundingDINO 等模型并由任务调度器动态分片，不依赖 X-AnyLabeling 或固定分组目录。

## 延期架构

- 图片数据集能力在视频重构后实现，不直接移植遗留分支路由。
- 在线标注已实现手动矩形框，以及 Ultralytics YOLO 和 Transformers GroundingDINO 自动标注；不依赖 X-AnyLabeling。
- 批量自动标注由 Worker 按任务启动时的启用 Frame 集合处理，不依赖外部 AnnotationBatch 目录。
- 不预建任意模型或训练脚本插件框架。
