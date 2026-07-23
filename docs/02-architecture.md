# 架构

状态：总体设计已批准，首次初始化和账号认证基础已实现。

## 当前仓库状态

当前仓库已有 Vue/FastAPI 初始化链路、账号认证与用户管理、两版 SQLite 迁移和安全路径组件；项目、媒体与独立 Worker 尚未实现。因此本页区分：

- 遗留架构：已经从 `dataset-manager-1` 代码验证的现状，仅作为重构输入。
- 当前基础：已经实现并验证的初始化链路。
- 目标设计：已经批准但尚未全部实现的职责划分和技术基线。

## 当前应用基础

```text
Vue setup/auth/admin pages
  ├─ /api/v1/setup/* → SetupService → HomePathResolver / WorkspaceLocator
  └─ /api/v1/auth + registrations + admin/users
       └─ AuthService
            ├─ Argon2 password verification
            ├─ SHA-256 token digest + SQLite sessions
            └─ User registration/status transitions
```

API 请求只负责校验和映射，工作区创建和认证状态流转由应用服务编排；数据库和管理员先写入同文件系统临时目录，再原子发布。初始化后认证服务立即启用，无需重启。该结构是后续模块的边界基线，不代表项目权限、审计表或持久任务 Worker 已存在。

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

## 已批准的目标架构

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
       ├─ Repository + Unit of Work
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

视频生命周期简化为：

`pending_download` → `ready` → `sampling_configured` → `sampled`

下载或抽帧失败记录在 Task，视频保留在可重试的前一状态；文件确实丢失时标记 `unavailable`。是否启用属于 Video，筛选由 Frame 推导，外部标注分组由 AnnotationBatch 表达，不再组合进视频状态。

任务状态与业务状态分离。下载、复制、抽帧、标注同步和导出使用 queued、running、succeeded、failed、canceled；任务记录包含类型、提交者、资源范围、进度、尝试次数、错误、租约、心跳和时间。

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
- Linux 原生使用 systemd，Windows 使用进程启动器，同时支持 Docker Compose。
- Docker 未提供 GPU 时正常启动并禁用训练/自动标注。
- 只支持单机本地磁盘，不支持跨服务器 Worker 或网络文件系统上的 SQLite。

## 延期架构

- 图片数据集能力在视频重构后实现，不直接移植遗留分支路由。
- 在线标注另行设计。
- 自动标注和可视化训练首批只支持 Ultralytics YOLO 检测模型。
- 内置自动标注由 Worker 动态切分 Frame，不依赖外部 AnnotationBatch 目录。
- 不预建任意模型或训练脚本插件框架。
