# 架构

状态：初始化、认证、项目权限、视频导入、采样、抽帧、筛帧、项目标签、在线矩形标注、模型项目、超参数模板、训练任务、自动标注和数据集导出已实现。

## 当前仓库状态

当前仓库已有 Vue/FastAPI 初始化链路、账号与项目权限、二十版 SQLite 迁移、安全路径组件、媒体、帧、项目标签、矩形标注、带标签的模型项目管理、不可变超参数模板、本地/远程模型推理、数据集导出、GPU 实时遥测和独立 Worker 训练调度器。

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
  │    └─ PyTorch CUDA / Ultralytics readiness
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
  │    └─ original-pixel rectangles + stable display order + annotation revision
  ├─ /api/v1/model-projects|models → ModelService
  │    ├─ 全局可见、创建者/管理员写入的归档项目与多标签分类
  │    ├─ 后台 `.pt` 导入、归档项目间移动与乐观并发
  │    └─ `.deleted/model-projects|models` 逻辑删除
  ├─ /api/v1/hyperparameter-* → HyperparameterTemplateService
  │    ├─ 工作区全局不可变模板、派生和逻辑删除
  │    └─ Detect v1 参数目录与严格 RAW YAML 校验
  ├─ /api/v1/training-* → TrainingService
  │    ├─ 全局草稿、冻结快照、生命周期操作与逻辑删除
  │    ├─ 单模型/单卡串行/多卡自定义序列
  │    └─ 独立指标/曲线、终端快照日志和训练模型项目发布
  ├─ /api/v1/me/x-anylabeling-server → XAnyLabelingSettingsService
  ├─ /api/v1/.../auto-annotations → AutoAnnotationService
       ├─ synchronous single-frame review draft
       ├─ local `.pt` YOLO or per-user X-AnyLabeling connection
       └─ persistent batch task creation without credential snapshots
  └─ /api/v1/projects/<id>/dataset-exports → DatasetExportService
       ├─ immutable label/source snapshots
       ├─ list/detail/streaming ZIP/logical delete
       └─ owner/editor writes + viewer reads/downloads

Independent Python Worker
  ├─ SQLite lease / progress / cancel / retry
  ├─ local copy + SHA-256 + ffprobe + FFmpeg thumbnail
  ├─ yt-dlp HTTP(S) download + remote identity deduplication
  ├─ FFmpeg frame extraction + atomic generation replacement
  ├─ inference model copy + atomic publication
  ├─ per-frame batch auto annotation + progress/status publication
  ├─ YOLO dataset hardlinks + labels/manifest + atomic publication
  └─ TrainingScheduler
       ├─ 每 GPU 一个非抢占 FIFO lane、跨 GPU 并行
       ├─ 独立 Python/Ultralytics 子进程 + JSONL 事件与回调故障隔离
       ├─ 运行级绝对路径 dataset.yaml 与工作区 Ultralytics 缓存
       └─ checkpoint 保留、指标入库和模型原子发布
```

API 请求负责校验、权限和应用服务编排。视频导入、抽帧、模型入库、批量自动标注、数据集导出和训练只创建持久状态并立即返回；外部工具和训练进程由独立 Worker 管理。训练启动前冻结数据集、超参和 basemodel 快照，启动后不允许修改原任务设置。

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
- 侧栏最近资源在 `AppShell` 挂载时形成会话快照，访问只持久化时间而不实时重排；复用的详情路由监听资源 ID，并拒绝过期响应覆盖当前 URL。
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

复制或下载失败记录在 Task，视频保留为 `pending` 供重试；文件确实不可用时预留 `unavailable`。采样不再改变视频生命周期：每个视频最多一个 SamplingPlan；方案版本未应用为 `configured`，当前版本已抽出帧为 `sampled`。帧启停保存于稳定 Frame 记录，并用 `frame_revision` 防止并发覆盖。列表中的业务状态由媒体状态、任务、采样版本、帧修订和标注存在性实时推导，不写入单独且不可逆的状态枚举。

任务状态与业务状态分离。复制、下载、抽帧、模型入库、批量自动标注和数据集导出使用 queued、running、succeeded、failed、canceled；任务记录包含类型、提交者、资源范围、进度、尝试次数、错误、取消标记、租约和时间。批量自动标注要求视频启用，并按 Worker 开始执行时启用的帧集合逐帧提交；失败或取消时保留已成功帧。导出记录另以 queued、running、ready、failed、canceled 表达产物状态，并关联持久任务。

采样方案覆盖使用 `none/configured/sampled` 三级确认，重新抽帧使用 `none/light/destructive` 三级确认。后端在写事务中根据当前帧、`frame_revision` 和标注存在性重新计算所需级别；前端状态过期导致风险升级时逐项拒绝。`extract_frames` 任务 queued/running 期间冻结方案、筛帧和标注写入，读取和播放不受影响；成功发布新一代帧后才删除旧帧及其级联标注。

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
- Worker 与 API 读取同一 SQLite 和工作区。复制、下载、抽帧和批量自动标注各自全局并发 2，模型入库和数据集导出各自全局并发 1；同类型每用户并发 1。每个 FFmpeg 抽帧进程限制 2 个线程，当前只部署一个调度 Worker。
- 项目媒体位于 `projects/<project UUID>/videos/<video short code>.<ext>`，缩略图位于 `projects/<project UUID>/thumbnails/<video short code>_thumbnail.jpg`，采样帧位于 `projects/<project UUID>/frames/<video short code>/<video short code>_frame_000001.<jpg|png>`；执行中输出位于顶层 `tmp/<task UUID>/`，验证后原子发布。短码在项目内唯一，帧文件可按原名平铺复制；每视频子目录仍是重采样原子替换边界。
- 数据集导出位于 `projects/<project UUID>/exports/<安全化名称>_YYYYMMDDHHMMSS[_N]/`；图像通过硬链接引用当前帧文件，类别和源数据快照、YOLO 标签、配置及统计清单随产物保存。下载按请求流式生成 ZIP，不在工作区保留额外压缩包。
- 训练子进程在 `<workspace>/cache/ultralytics/` 运行；Ultralytics 的 AMP 辅助权重等运行缓存不会写入源码目录。每次运行在自身目录生成解析为绝对路径的 `dataset.yaml`，避免相对路径随子进程工作目录漂移。
- Linux 原生使用 systemd，Windows 使用进程启动器，同时支持 Docker Compose。
- Docker 未提供 GPU 时正常启动并禁用训练/自动标注。
- Python 核心依赖不包含本地大模型运行库；GPU 服务器通过 uv 的 `gpu` extra 安装 CUDA 12.8 PyTorch、torchvision 和 Ultralytics。远程模型依赖只存在于 X-AnyLabeling-Server。
- 只支持单机本地磁盘，不支持跨服务器 Worker 或网络文件系统上的 SQLite。

当前及后续工作区目录约定：

```text
projects/<project UUID>/
├─ videos/<video short code>.<ext> # 已实现：受管原始视频
├─ thumbnails/<video short code>_thumbnail.jpg
├─ frames/<video short code>/      # 已实现：当前一代规范采样帧
│  └─ <video short code>_frame_000001.<jpg|png>
├─ annotation-batches/<batch UUID>/ # 逻辑概念：当前批量任务直接按 Frame 记录处理，不物化固定分组目录
└─ exports/<安全化名称>_YYYYMMDDHHMMSS[_N]/ # 已实现：不可变 YOLO 数据集导出

models/<model UUID>/                # 已实现：受管 `.pt` YOLO 模型文件
```

遗留 `thumbnails/` 对应新的项目级 `thumbnails/`；遗留 `dataset/` 对应新的 `exports/<安全化名称>_YYYYMMDDHHMMSS[_N]/`；遗留 `groups/` 不作为普通数据目录照搬，而对应自动标注任务的帧快照/分片概念。新系统本地只加载 YOLO；大模型通过 X-AnyLabeling-Server 的 `/v1/models` 与 `/v1/predict` 解耦运行。

## 延期架构

- 图片数据集能力在视频重构后实现，不直接移植遗留分支路由。
- 在线标注已实现手动矩形框、本地 Ultralytics YOLO 和 X-AnyLabeling-Server 自动标注；远程返回只接纳轴对齐矩形。
- 批量自动标注由 Worker 按任务启动时的启用 Frame 集合处理，不依赖外部 AnnotationBatch 目录。
- 不预建任意模型或训练脚本插件框架。
