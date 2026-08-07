# 数据库

状态：工作区 SQLite、账号/会话、项目/成员、项目标签、视频、任务、采样方案、帧、矩形标注、模型项目、超参数模板、训练任务/模型/运行/指标、用户远程配置、推理模型和数据集导出迁移已实现。

## 数据库选型

新项目使用一个工作区 SQLite 数据库，通过 SQLAlchemy 访问、Alembic 迁移。用户、权限、项目、媒体、帧、标注批次、导出、任务和审计记录全部存储在该数据库，不再为每个项目创建独立数据库。

- 数据库位于 `.vision-dataset-workbench/db/workbench.sqlite3`。
- 仅支持本机磁盘，不支持 NFS、SMB 等网络文件系统。
- 运行库包含 SQLite WAL-reset 修复时启用 WAL，否则使用 rollback journal。
- 开启 foreign keys 和 busy timeout，禁止长事务包围文件复制或外部命令。

## 当前 schema

Alembic `0001_initial` 至 `0014_model_projects` 建立账号、项目、媒体、采样、标注、导出、模型和远程配置基础；`0015_model_management` 完善模型项目管理并把 `import_model` Task 迁移到全局模型项目；`0016_hyperparameter_templates` 增加不可变超参数模板；`0017_training_core` 建立训练核心表和发布来源关系；`0018_training_action_requests` 保存生命周期操作幂等结果；`0019_add_dfl_loss` 增加 Detect 的 dfl loss 指标；`0020_add_model_project_tags` 增加模型项目多标签关系，并为已有项目回填“未分类”。当前 `users` 表为：

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

owner 由 `projects.creator_id` 推导，不创建成员行，因此不能通过成员接口转移、降级或移除。创建项目时同步创建空的 `projects/<project UUID>/` 目录；`videos/` 和 `thumbnails/` 由 Worker 首次发布对应文件时创建。仅 owner 可删除项目，且项目存在 queued/running 任务时拒绝删除。删除前在项目目录生成当前 schema 的完整 `project_metadata.json`，再将目录移动到 `.deleted/projects/<project UUID>/project/`，最后删除 `projects` 记录并由外键级联删除关联数据；快照不承诺兼容未来 schema，也不提供恢复入口。

`labels` 表保存项目级目标检测类别：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `project_id` | 标签 UUID 及所属项目；项目删除时级联删除 |
| `name` / `name_normalized` | 1–64 位规范英文类别；项目内不区分大小写唯一 |
| `description_zh` | 可选中文显示说明，最长 64 字符；不参与模型提示词和导出映射 |
| `color` | 六位十六进制标注框颜色 |
| `sort_order` | 非负排序；导出 YOLO 时据此生成从 0 开始的类别编号 |
| `enabled` | 是否允许新增该类别标注；停用不删除未来历史标注 |
| `version` / 时间字段 | 乐观并发版本和创建、更新时间 |

内部标注关联标签 UUID，不持久化 YOLO 数字类别编号。已被任意矩形标注引用的标签受外键限制，删除接口返回 409；未使用标签仍可删除并自动压缩后续映射顺序。

`videos` 表保存受管原始视频：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `project_id` | 视频 UUID 及所属项目外键 |
| `short_code` | 8 位项目内唯一不可变短码；使用 `0123456789ABCDEFGHJKMNPQRSTVWXYZ`，用于显示和受管文件命名 |
| `source_type` | `local` 或 `remote` |
| `title` / `source_name` / `source_url` | 显示标题、原文件名和规范化远程 URL |
| `extractor` / `external_id` | yt-dlp 提取器与原始媒体 ID；项目内组合唯一 |
| `content_sha256` | 本地文件完整 SHA-256；项目内唯一 |
| `file_path` / `thumbnail_path` | 工作区内相对路径，不保存导入源绝对路径 |
| `duration` / `width` / `height` / `fps` / `total_frames` / `file_size` | ffprobe 与文件系统确认的媒体元数据 |
| `status` | `pending`、`ready` 或 `unavailable` |
| `enabled` | 视频是否进入后续标注、自动标注和导出；默认启用 |
| `version` / 时间字段 | 资源版本和创建、更新时间 |

短码与视频 UUID 保存在同一条 Video 记录中；UUID 继续作为主键、外键和 API 路由身份。短码由服务端在创建导入任务时生成，数据库以 `(project_id, short_code)` 唯一索引和格式 CHECK 约束兜底，冲突只重试短码分配。本地重复内容和远程重复身份通过 SQLite partial unique index 约束。每个项目最多保存 999 条 Video：导入服务先检查剩余容量并返回逐项 accepted/rejected，SQLite `trg_videos_project_limit` 插入触发器处理多用户并发越过前置检查的竞争场景。复制/下载成功前视频保持 `pending`；Worker 验证文件与元数据后才写入受管路径并切换为 `ready`。

视频 `enabled` 与媒体 `status` 相互独立。停用不删除文件、不取消任务，也不阻止播放、采样配置、抽帧、筛帧或手动/单张自动标注；停用视频不能新建批量自动标注任务，Worker 只处理开始执行时启用的帧，后续导出也必须显式过滤 `enabled = true`。备注、遗留自由文本 `status_info` 和不可逆业务状态枚举不进入新 schema；列表业务状态由任务、视频、采样版本、帧修订及标注存在性推导。

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
| `annotation_revision` | 当前整帧标注版本；整帧替换时用于乐观并发 |
| `created_at` | 当前代次发布时间 |

Frame 使用 `(video_id, sequence)` 唯一索引覆盖视频内排序和查找；布尔 `enabled` 与单列 `video_id` 不再建立冗余索引。重采样先在任务临时目录生成并验证全部文件，再替换 `frames/<video short code>/` 并在同一数据库事务中重建 Frame 记录。帧文件名为 `<video short code>_frame_<六位序号>.<jpg|png>`，可在同一项目内平铺复制而不重名。失败、取消或方案版本改变时保留上一代目录和记录。

覆盖风险不新增冗余计数列：`extracted_frames > 0` 表示已有帧，`frame_revision > 1` 表示当前代次保存过筛帧变更，是否已有标注通过 `frames` 与 `annotations` 的索引关联查询判断。重新抽帧成功后 Frame 重建会级联删除旧标注，并把新帧全部初始化为启用。

`annotations` 表保存当前帧的轴对齐矩形框：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `frame_id` / `label_id` | 标注 UUID、帧和项目标签关系；删帧级联，删已引用标签受限 |
| `x_min` / `y_min` / `x_max` / `y_max` | 原始图片像素整数坐标，满足非负且最大值大于最小值 |
| `source` | `manual` 或 `model` |
| `confidence` | 模型标注可空置信度；手工标注为空 |
| `sort_order` | 帧内从 0 开始的稳定显示和图层顺序；后创建的框位于更高图层 |
| `created_at` | 当前标注创建时间 |

客户端按整帧读取和替换标注；请求必须携带当前 `annotation_revision`。服务端校验所有标签属于同一项目、矩形在图片边界内且 ID 不重复，按请求数组顺序重建 `sort_order`，成功后整体替换并递增修订号。

`model_projects` 表保存工作区全局模型系列：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `name` | 模型项目 UUID 和名称 |
| `series_type` | `archive` 或 `training` |
| `system_key` | 可空唯一系统标识；`temporary` 对应兼容登记入口 |
| `created_at` | 创建时间 |

`model_project_tags` 保存工作区全局标签名称，`model_project_tag_links` 以 `(model_project_id, tag_id)` 复合主键保存多对多关系。每个模型项目必须有 1–20 个标签；迁移为既有项目关联“未分类”，训练任务自动发布的项目关联“训练”。

`inference_models` 表保存全局受管推理模型：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `model_project_id` | 模型 UUID 和模型项目外键 |
| `name` / `description` | 可编辑显示名和描述基础字段 |
| `parameters` | JSON 文本；保留训练超参数和模型参数信息 |
| `kind` | 当前固定为 `yolo` |
| `status` | `copying`、`ready` 或 `failed`；ready 表示入库完成，首次推理仍会验证运行兼容性 |
| `storage_path` / `source_name` | 工作区内受管路径及不含绝对路径的来源显示名 |
| `created_by_id` | 登记模型的系统管理员 |
| `error` | 入库失败的安全错误信息 |
| 时间字段 | 创建和更新时间 |

模型属于工作区而非单个数据集项目；旧模型迁移和兼容登记模型均归入固定“临时模型项目”。

`hyperparameter_templates` 保存工作区全局 YOLO Detect 训练配置：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `name` / `name_normalized` | 模板 UUID、显示名和活动模板内不区分大小写的唯一名 |
| `epochs` / `batch_size` / `image_size` | 三项核心训练参数；batch 支持正整数、`auto` 或合法比例 |
| `parameters` | 经过 Detect v1 参数目录校验和规范化的扩展参数 JSON；不重复保存三项核心参数 |
| `catalog_version` | 解析该模板所用参数目录版本，当前为 `detect-v1` |
| `derived_from_id` | 可空派生来源；删除来源模板时保留历史关系 |
| `created_by_id` / `is_system` | 创建者和只读系统模板标记 |
| `created_at` / `deleted_at` | 创建时间和逻辑删除时间；模板内容创建后不可修改 |

模板删除仅对非系统、非活动引用资源开放；普通列表过滤 `deleted_at`。名称在逻辑删除后可复用，但模板 UUID 与派生关系不复用。

训练数据拆成四个层级，避免任务配置、模型配置、每次尝试和 epoch 指标相互覆盖：

| 表 | 关键语义 |
| --- | --- |
| `training_tasks` | UUID 主键；`code` 全局唯一且逻辑删除后不复用；保存名称、模式、默认资源、聚合状态/进度、创建者、版本和训练时间 |
| `training_models` | 一个任务 1–10 个模型；保存显式资源、三项核心覆盖、GPU、lane 顺序、冻结快照、产物 code，以及派生/追加来源 |
| `training_runs` | 每次 initial/retry/resume/extend 独立一行；保存 attempt、GPU、PID、token、事件游标、epoch、路径、主机快照、租约和终态信息 |
| `training_metrics` | `(training_run_id, epoch)` 复合主键；保存 box/cls/dfl loss、学习率、precision、recall、mAP50、mAP50-95 和可选 P-R 数据 |

任务状态为 `draft/queued/running/canceling/canceled/start_failed/failed/partial/succeeded`；模型和运行不含 `partial`。`(task_id,gpu_index,queue_order)` 唯一，GPU lane 顺序从 1 开始；SQLite 部分唯一索引确保每张 GPU 最多一个 `running/canceling` run。任务进度是所有模型 epoch 进度的等权聚合，列表按 `last_run_at` 倒序。

启动成功前草稿仍可编辑；启动事务解析默认值，校验 ready 数据集/模型和活动模板，随后冻结三个 JSON 快照、不可变 artifact code 和 initial run。`model_projects.training_task_id` 与 `inference_models.training_model_id` 都是唯一可空来源关系，确保一个训练任务最多发布一个训练项目、一个训练模型最多对应一个发布模型。

`training_action_requests` 以 `(actor_id, action, idempotency_key)` 唯一，保存 action API 已创建的 task/run ID。它只提供请求重放保护，不替代训练状态机校验。

训练逻辑删除保留数据库审计记录并将受管运行目录移入 `.deleted/training-tasks|training-models/`。任务删除保留已发布模型；删除已发布子模型要求显式确认，并同时逻辑删除发布模型。当前不提供 `.deleted` 恢复、导入或自动清理。

`user_xanylabeling_settings` 以 `user_id` 为主键保存每个用户的 `server_url`、可空 `api_key_ciphertext` 和时间字段。API 密钥使用部署级 `VDW_CREDENTIAL_ENCRYPTION_KEY` 加密，表中不保存明文；删除用户时配置级联删除。远程模型目录不写入本表或 `inference_models`。

`dataset_exports` 表保存项目级不可变导出记录：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `project_id` / `created_by_id` | 导出 UUID、项目和创建者外键 |
| `task_id` | 可空且唯一的关联持久任务；任务删除时置空 |
| `name` / `status` | 用户展示名称；`queued`、`running`、`ready`、`failed` 或 `canceled` |
| `train_ratio` / `actual_train_ratio` | 期望及完成后的实际训练集比例 |
| `total_frames` / `train_frames` / `val_frames` | 完成后的样本统计 |
| `label_snapshot` / `source_snapshot` | 创建任务时冻结的类别映射和参与视频修订快照 JSON |
| `manifest` / `storage_path` | 完成后的清单 JSON 和工作区相对产物路径 |
| `error` / 时间字段 | 安全错误信息、创建、开始、完成、逻辑删除和更新时间 |

同一项目通过 partial unique index 只允许一个 `queued` 或 `running` 导出。正常查询过滤 `deleted_at`；逻辑删除保留记录，并把产物移动至工作区 `.deleted/`。

`tasks` 表当前承载 `copy_video`、`download_video`、`extract_frames`、`import_model`、`auto_annotate` 和 `export_dataset`：

| 字段 | 约束/含义 |
| --- | --- |
| `id` / `project_id` / `submitted_by_id` / `video_id` | 任务、项目、提交者和目标视频关系 |
| `type` | 视频复制/下载、抽帧、模型入库、批量自动标注或数据集导出 |
| `status` | `queued`、`running`、`succeeded`、`failed` 或 `canceled` |
| `payload` / `result` | JSON 文本；分别保存执行输入和最终摘要 |
| `progress` / `error` / `cancel_requested` | 0–100 进度、安全错误文本和协作取消标记 |
| `attempts` / `retry_of_id` | 实际领取次数和重试来源 |
| `lease_owner` / `lease_expires_at` | Worker 租约；过期的 running 任务可重新排队 |
| 时间字段 | 创建、开始、结束和更新时间 |

同一视频只允许一个 queued/running 任务；数据集导出另由 `dataset_exports` 的项目级索引串行化。视频复制、下载和抽帧可通过重试接口创建新 Task 并保留原记录；模型入库、批量自动标注和数据集导出不提供通用重试按钮，需由用户重新发起以明确当次参数和快照。批量自动标注逐帧独立提交，失败或取消不会回滚此前成功帧；导出失败或取消不发布残缺目录。

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
