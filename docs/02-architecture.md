# 架构

状态：总体设计已批准，初始化、认证、项目权限和视频导入/播放主链路已实现。

## 当前仓库状态

当前仓库已有 Vue/FastAPI 初始化链路、账号与项目权限、四版 SQLite 迁移、安全路径组件、媒体资源和独立 Worker。采样、帧、标注批次、导出和 GPU 能力仍是目标设计。因此本页区分：

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
  ├─ /api/v1/filesystem → HomePathResolver
  └─ /api/v1/projects/<id>/videos|imports|tasks → MediaService
       ├─ SQLite Video / Task state
       ├─ authenticated playback, Range and download
       └─ workspace/projects/<project UUID>

Independent Python Worker
  ├─ SQLite lease / progress / cancel / retry
  ├─ local copy + SHA-256 + ffprobe + FFmpeg thumbnail
  └─ yt-dlp HTTP(S) download + remote identity deduplication
```

API 请求只负责校验和映射，工作区创建、认证状态流转、项目授权和媒体命令由应用服务编排；数据库和管理员先写入同文件系统临时目录，再原子发布。视频导入请求只创建持久任务并立即返回，文件复制、下载和媒体探测在独立 Worker 中执行。审计表、采样帧和导出尚未实现。

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
       ├─ Project / Video / Frame / AnnotationBatch / Export
       ├─ SQLAlchemy services（当前）
       ├─ Storage Gateway
       └─ Task Gateway
              │
      ┌───────┴────────┐
      ▼                ▼
SQLite             Persistent Worker
                       ├─ yt-dlp
                       ├─ FFmpeg / ffprobe
                       ├─ 标注批次物化/同步
                       └─ 数据集导出
              │
              ▼
       Controlled Storage Root
```

### 前端职责

- 路由页面只组织用户流程，不直接实现业务算法。
- 项目、媒体、帧、任务、标注批次和导出使用独立的功能模块。
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

复制或下载失败记录在 Task，视频保留为 `pending` 供重试；文件确实不可用时预留 `unavailable`。采样、启停和帧筛选状态将在对应领域表实现，外部标注分组由 AnnotationBatch 表达，不再组合进视频状态。

任务状态与业务状态分离。当前复制、下载使用 queued、running、succeeded、failed、canceled；任务记录包含类型、提交者、资源范围、进度、尝试次数、错误、取消标记、租约和时间。抽帧、标注同步和导出后续复用该状态模型。

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
- Worker 与 API 读取同一 SQLite 和工作区。本地复制与远程下载分别全局并发 2，同类型每用户并发 1；当前只部署一个调度 Worker。
- 项目媒体位于 `projects/<project UUID>/videos/`，缩略图位于 `projects/<project UUID>/thumbnails/`；执行中输出位于顶层 `tmp/<task UUID>/`，验证后原子发布。
- Linux 原生使用 systemd，Windows 使用进程启动器，同时支持 Docker Compose。
- Docker 未提供 GPU 时正常启动并禁用训练/自动标注。
- 只支持单机本地磁盘，不支持跨服务器 Worker 或网络文件系统上的 SQLite。

当前及后续项目目录约定：

```text
projects/<project UUID>/
├─ videos/                         # 已实现：受管原始视频
├─ thumbnails/                     # 已实现：视频缩略图
├─ frames/<video UUID>/            # 计划：规范采样帧
├─ labels/<video UUID>/            # 计划：规范标签
├─ annotation-batches/<batch UUID>/ # 计划：外部并行标注批次
└─ exports/<export UUID>/           # 计划：不可变数据集导出
```

遗留 `thumbnails/` 对应新的项目级 `thumbnails/`；遗留 `dataset/` 对应后续 `exports/<export UUID>/`；遗留 `groups/` 不作为普通数据目录照搬，而对应后续 `annotation-batches/<batch UUID>/`。后者保留将采样帧分片、并行启动多个 X-AnyLabeling/DINO 实例的用途；内置自动标注直接由任务调度器分片，不依赖该物化目录。

## 延期架构

- 图片数据集能力在视频重构后实现，不直接移植遗留分支路由。
- 在线标注另行设计。
- 自动标注和可视化训练首批只支持 Ultralytics YOLO 检测模型。
- 内置自动标注由 Worker 动态切分 Frame，不依赖外部 AnnotationBatch 目录。
- 不预建任意模型或训练脚本插件框架。
