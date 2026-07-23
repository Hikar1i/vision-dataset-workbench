# 数据库

状态：工作区 SQLite 和首个 `users` 迁移已实现；其余领域 schema 仍为批准设计。

## 数据库选型

新项目使用一个工作区 SQLite 数据库，通过 SQLAlchemy 访问、Alembic 迁移。用户、权限、项目、媒体、帧、标注批次、导出、任务和审计记录全部存储在该数据库，不再为每个项目创建独立数据库。

- 数据库位于 `.vision-dataset-workbench/db/workbench.sqlite3`。
- 仅支持本机磁盘，不支持 NFS、SMB 等网络文件系统。
- 运行库包含 SQLite WAL-reset 修复时启用 WAL，否则使用 rollback journal。
- 开启 foreign keys 和 busy timeout，禁止长事务包围文件复制或外部命令。

## 当前 schema

首次初始化通过 Alembic `0001_initial` 创建 `users` 表：

| 字段 | 约束/含义 |
| --- | --- |
| `id` | UUID 字符串主键 |
| `username` | 唯一索引，最长 64 字符 |
| `password_hash` | Argon2 密码哈希 |
| `status` | 当前首个管理员写入 `active` |
| `is_system_admin` | 系统管理员标记 |
| `created_at` | 创建时间 |

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

当前普通应用重启只验证定位文件指向的 `db/workbench.sqlite3` 存在；自动升级已有工作区尚未实现。

## 遗留项目

不实现遗留数据库、目录或配置导入工具。需要时由用户按新系统流程手动导入媒体并重新建立项目。
