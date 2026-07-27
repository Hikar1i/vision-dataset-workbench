# 数据库

状态：工作区 SQLite、账号/会话、项目/成员、项目标签、视频、任务、采样方案和帧迁移已实现；标注记录和导出 schema 仍为批准设计。

## 数据库选型

新项目使用一个工作区 SQLite 数据库，通过 SQLAlchemy 访问、Alembic 迁移。用户、权限、项目、媒体、帧、标注批次、导出、任务和审计记录全部存储在该数据库，不再为每个项目创建独立数据库。

- 数据库位于 `.vision-dataset-workbench/db/workbench.sqlite3`。
- 仅支持本机磁盘，不支持 NFS、SMB 等网络文件系统。
- 运行库包含 SQLite WAL-reset 修复时启用 WAL，否则使用 rollback journal。
- 开启 foreign keys 和 busy timeout，禁止长事务包围文件复制或外部命令。

## 当前 schema

Alembic `0001_initial` 创建基础 `users` 表，`0002_authentication` 增加规范化用户名、审批信息和服务端会话，`0003_projects` 增加项目与成员关系，`0004_media_tasks` 增加视频与持久任务，`0005_sampling_frames` 增加采样方案和稳定帧记录，`0006_video_enabled_limit` 增加视频启用状态和项目容量硬约束，`0007_labels` 增加项目标签。当前 `users` 表为：

| 字段 | 约束/含义 |
| --- | --- |
| `id` | UUID 字符串主键 |
| `username` | 用户显示名，最长 64 字符 |
| `username_normalized` | 小写登录名，唯一索引；确保用户名大小写不重复 |
| `password_hash` | Argon2 密码哈希 |
| `status` | `pending`、`active`、`rejected` 或 `disabled` |
| `is_system_admin` | 系统管理员标记 |
| `created_at` | 创建时间 |
| `updated_at` | 最后修改时间 |
| `reviewed_at` / `reviewed_by_id` | 最近审批/状态操作时间及管理员 |

`sessions` 表为：

| 字段 | 约束/含义 |
| --- | --- |
| `id` | UUID 字符串主键 |
| `user_id` | 用户外键；删除用户时级联删除会话 |
| `token_hash` | 原始随机 Cookie 的 SHA-256 摘要，唯一索引 |
| `created_at` / `last_seen_at` | 创建和最近触达时间 |
| `idle_expires_at` | 12 小时空闲到期时间 |
| `absolute_expires_at` | 创建后 7 天绝对到期时间 |

SQLite 不保留时区偏移，当前认证表按 naive UTC 持久化，API 输出时明确追加 UTC 语义。

`projects` 表为：

| 字段 | 约束/含义 |
| --- | --- |
| `id` | UUID 字符串主键，同时作为受管项目目录名 |
| `name` | 1–128 字符；允许不同项目重名 |
| `description` | 最长 2000 字符 |
| `creator_id` | 创建者外键，删除受限；该用户是永久 owner |
| `version` | 从 1 开始的乐观并发版本 |
| `created_at` / `updated_at` | 创建和最近修改时间 |

`project_memberships` 只保存非所有者成员：

| 字段 | 约束/含义 |
| --- | --- |
| `project_id` / `user_id` | 复合主键；同一用户不能重复加入项目 |
| `role` | 仅允许 `editor` 或 `viewer` |
| `created_at` | 加入项目时间 |

owner 由 `projects.creator_id` 推导，不创建成员行，因此不能通过成员接口转移、降级或移除。创建项目时同步创建空的 `projects/<project UUID>/` 目录；`videos/` 和 `thumbnails/` 由 Worker 首次发布对应文件时创建。当前尚无项目删除流程。

`labels` 表保存项目级目标检测类别：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `project_id` | 标签 UUID 及所属项目；项目删除时级联删除 |
| `name` / `name_normalized` | 1–64 位规范英文类别；项目内不区分大小写唯一 |
| `color` | 六位十六进制标注框颜色 |
| `sort_order` | 非负排序；导出 YOLO 时据此生成从 0 开始的类别编号 |
| `enabled` | 是否允许新增该类别标注；停用不删除未来历史标注 |
| `version` / 时间字段 | 乐观并发版本和创建、更新时间 |

内部标注将关联标签 UUID，不持久化 YOLO 数字类别编号。当前标注记录表尚未实现，因此现阶段所有标签都属于“未被使用”并可删除；标注表落地时必须增加已引用标签拒删测试。

`videos` 表保存受管原始视频：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `project_id` | 视频 UUID 及所属项目外键 |
| `source_type` | `local` 或 `remote` |
| `title` / `source_name` / `source_url` | 显示标题、原文件名和规范化远程 URL |
| `extractor` / `external_id` | yt-dlp 提取器与原始媒体 ID；项目内组合唯一 |
| `content_sha256` | 本地文件完整 SHA-256；项目内唯一 |
| `file_path` / `thumbnail_path` | 工作区内相对路径，不保存导入源绝对路径 |
| `duration` / `width` / `height` / `fps` / `total_frames` / `file_size` | ffprobe 与文件系统确认的媒体元数据 |
| `status` | `pending`、`ready` 或 `unavailable` |
| `enabled` | 视频是否进入后续标注、自动标注和导出；默认启用 |
| `version` / 时间字段 | 资源版本和创建、更新时间 |

本地重复内容和远程重复身份通过 SQLite partial unique index 约束。每个项目最多保存 999 条 Video：导入服务先检查剩余容量并返回逐项 accepted/rejected，SQLite `trg_videos_project_limit` 插入触发器处理多用户并发越过前置检查的竞争场景。复制/下载成功前视频保持 `pending`；Worker 验证文件与元数据后才写入受管路径并切换为 `ready`。

视频 `enabled` 与媒体 `status` 相互独立。停用不删除文件、不取消任务，也不阻止播放、采样配置、抽帧或帧管理；后续标注与导出实现必须显式过滤 `enabled = true`。备注和遗留自由文本 `status_info` 不进入新 schema，状态信息由任务、视频和采样方案结构化字段推导。

`sampling_plans` 每个视频最多一行：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `video_id` | 方案 UUID 和唯一视频外键 |
| `mode` / `parameters` | `target_frames`、`frame_interval` 或 `time_interval` 及规范化参数 JSON |
| `output_format` / `output_quality` | JPG 质量 1–31，或 PNG 压缩级别 0–9 |
| `computed_interval` / `expected_frames` | 计算后的帧间隔和可预测目标数量 |
| `extracted_frames` / `enabled_frames` | 当前已发布帧和启用帧计数 |
| `version` / `applied_version` | 当前方案版本及已成功抽帧的方案版本 |
| `generation` | 成功发布一代帧后递增 |
| `frame_revision` | 批量启停成功后递增，用于乐观并发 |
| 时间字段 | 创建和更新时间 |

`frames` 表保存当前一代采样帧：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `video_id` | 稳定帧 UUID 和视频外键 |
| `generation` / `sequence` | 所属发布代次和从 1 开始的视频内唯一序号 |
| `source_frame_index` / `time_offset` | 原视频帧位置和秒偏移 |
| `file_path` | 工作区内相对图片路径 |
| `enabled` | 帧是否进入后续流程 |
| `created_at` | 当前代次发布时间 |

重采样先在任务临时目录生成并验证全部文件，再替换 `frames/<video UUID>/` 并在同一数据库事务中重建 Frame 记录。失败、取消或方案版本改变时保留上一代目录和记录。

`tasks` 表当前承载 `copy_video`、`download_video` 和 `extract_frames`：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `project_id` / `submitted_by_id` / `video_id` | 任务、项目、提交者和目标视频关系 |
| `type` | `copy_video`、`download_video` 或 `extract_frames` |
| `status` | `queued`、`running`、`succeeded`、`failed` 或 `canceled` |
| `payload` / `result` | JSON 文本；分别保存执行输入和最终摘要 |
| `progress` / `error` / `cancel_requested` | 0–100 进度、安全错误文本和协作取消标记 |
| `attempts` / `retry_of_id` | 实际领取次数和重试来源 |
| `lease_owner` / `lease_expires_at` | Worker 租约；过期的 running 任务可重新排队 |
| 时间字段 | 创建、开始、结束和更新时间 |

同一视频只允许一个 queued/running 任务。重试创建新 Task 并复用原 Video，保留失败或取消记录用于追踪。

初始化服务先在目标父目录创建同文件系统临时目录，执行迁移并写入管理员，成功后原子重命名为 `.vision-dataset-workbench`。定位文件写入失败时会删除未发布工作区，口令保持可重试。

## 遗留数据库基线

遗留项目使用一个管理 SQLite 和每项目一个 SQLite。

### 管理数据库

代码定义的 `projects` 表包含：

| 字段 | 含义 |
| --- | --- |
| `project_id` | 项目主键 |
| `name` | 唯一项目名 |
| `description` | 描述 |
| `root_path` | 项目根目录 |
| `db_path` | 项目数据库路径 |
| `created_at` / `updated_at` | 时间戳 |

实际参考数据库还存在 `dataset_type`，并同时包含 video 与 image 记录，但当前 `develop` 代码没有稳定管理该字段。这是历史/分支差异，不是新项目 schema。

### 项目数据库

- `project_info`：项目 ID、名称、描述、根路径和创建时间。
- `videos`：视频身份、来源、媒体信息、启用状态、业务状态、采样参数、帧位图、备注、播放列表信息和时间戳。
- `settings`：项目级键值设置。

`group_id`、`frame_bitmap` 及旧 ID/`enabled` 迁移由视频列表查询临时执行。部分异常被忽略，没有 schema 版本表、外键或业务索引。这些行为只用于理解历史数据，不得在新实现中复用。

### 图片分支表

延期实现的图片分支包含以下原型表：

- `images`：文件、标签相对路径、拆分、启用状态、宽高。
- `image_label_mappings`：类别 ID 到类别名。
- `duplicate_groups`：去重方法、相似度和保留图片。
- `duplicate_group_items`：重复组成员及移动结果。

它们是需求证据，不是已批准的新 schema。

## 遗留数据注意事项

- 项目数据库可能随项目目录移动；重新读取时遗留代码会修改 `root_path`。
- 视频 `frame_bitmap` 使用 LSB-first；空值代表所有帧启用。
- 位图位置依赖目录中文件排序，文件变化会改变其语义。
- 本地视频 ID 是全文件 MD5 的 Base64URL 截断值。
- 项目删除只删管理数据库注册，不删除项目文件或项目数据库。
- 同一历史目录中可能存在不同版本的 schema。

## 新实现的数据概念

第一阶段至少需要表达：

| 概念 | 最小职责 |
| --- | --- |
| Dataset Project | 项目身份、类型、存储位置、生命周期 |
| User / Session | 内置账号和服务端浏览器会话 |
| Registration State | User 的 pending、active、rejected、disabled 状态 |
| Project Membership | owner、editor、viewer 项目权限 |
| Project Label | 英文类别名、颜色、顺序、启用状态和稳定 UUID |
| Video Asset | 来源、稳定身份、媒体元数据、业务状态、启用状态 |
| Frame Asset | 稳定帧身份、视频关系、序号/时间、文件引用、启用状态 |
| Sampling Plan | 模式、输入参数、计算结果和版本 |
| Annotation Batch / Item | 外部标注批次、帧快照、标签基线和同步状态 |
| Export | 导出参数、输出位置、结果摘要和任务关系 |
| Task | 类型、提交者、状态、进度、重试、错误、租约和心跳 |
| Project Setting | 类型化或受约束的项目配置 |
| Audit Event | 认证、权限和关键资源操作记录 |

系统管理员与项目角色分开。首批只实现系统管理员及 owner/editor/viewer，不预建组织、用户组或 ABAC。

## 关系与约束要求

- 业务关系使用 SQLite 外键和显式唯一约束。
- 项目内自然唯一性必须显式表达，例如视频来源幂等键、帧序号和导出名称规则。
- 任务领取需要支持原子竞争、租约过期和重试计数。
- 媒体文件只在数据库保存受控存储根下的相对引用，不保存客户端提交的任意服务端绝对路径。
- 帧启停绑定稳定 Frame 记录，不继续用目录位置位图作为唯一事实来源。
- 标注关联项目标签 UUID；YOLO 数字类别编号只在导出时按当前排序生成。
- AnnotationBatch 保存帧 ID 与标签基线；其物化目录不是事实来源。
- Export 保存不可变帧与标签清单，不受后续项目修改影响。
- 时间统一保存为带时区的 UTC 时间，API 输出采用 ISO 8601。

## 迁移规则

- 所有 schema 变更使用版本化迁移文件，并进入代码评审。
- 应用启动可以检查迁移版本，但普通读取接口不得执行 DDL。
- 生产升级先备份、再迁移、再启动新版本；回滚能力必须在部署文档中说明。
- 迁移应在空库和前一受支持版本的真实样本上测试。
- 破坏性迁移需要显式数据转换和验证查询，禁止吞掉错误继续运行。

正常首次启动不需要手工执行迁移，初始化 API 会运行 Alembic。开发或修复时可显式指定目标数据库：

```bash
cd backend
VDW_DATABASE_URL=sqlite:////absolute/path/to/workbench.sqlite3 uv run alembic upgrade head
```

应用启动会先确认定位文件指向的 `db/workbench.sqlite3` 存在，再执行 Alembic `upgrade head` 并建立认证服务。发布前仍必须按部署流程备份；普通资源读取接口不会执行 DDL。

## 遗留项目

不实现遗留数据库、目录或配置导入工具。需要时由用户按新系统流程手动导入媒体并重新建立项目。
