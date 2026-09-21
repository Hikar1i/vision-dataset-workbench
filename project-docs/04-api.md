# API

## 2026-08 新增接口

- 项目批量自动标注：POST /api/v1/projects/{id}/auto-annotations/batch。
- 按标注启停：POST /api/v1/projects/{id}/videos/batch-enabled-by-annotation。
- 当前用户大模型配置：GET/POST/PATCH/DELETE /api/v1/me/llm-configs，默认参数使用 /defaults，连接测试使用 /{id}/test。
- Overview 看板：GET /api/v1/overview，返回个人统计、脱敏全局训练负载和任务状态汇总。
- 在线标注支持 source=online，通过当前用户配置调用 OpenAI-compatible /chat/completions，使用内置目标检测提示词。

状态：`/api/v1` 初始化、认证、用户、项目、项目标签、运行能力、文件浏览、视频导入、任务、采样方案、帧、矩形标注、推理模型、自动标注和数据集导出接口已实现。

## 当前接口

| 方法与路径 | 认证 | 用途 |
| --- | --- | --- |
| `GET /api/v1/health` | 无 | 进程存活检查，返回 `{"status":"ok"}` |
| `GET /api/v1/capabilities` | Session | 返回缓存的 GPU、PyTorch CUDA、Ultralytics 与功能能力 |
| `GET /api/v1/setup/status` | 无 | 返回工作区是否已初始化 |
| `GET /api/v1/setup/directories` | `X-Setup-Token` | 分页浏览启动用户 `~` 内目录；支持当前目录 `search` 包含过滤 |
| `POST /api/v1/setup/directories` | `X-Setup-Token` | 在受控父目录中新建目录 |
| `POST /api/v1/setup/initialize` | `X-Setup-Token` | 创建工作区和首个管理员 |
| `GET /api/v1/auth/status` | 无 | 返回 `multi/single` 运行模式 |
| `POST /api/v1/auth/login` | 同源 | 登录并设置 `vdw_session` Cookie |
| `GET /api/v1/auth/me` | Session | 返回当前安全用户字段 |
| `POST /api/v1/auth/logout` | 同源 | 存在 Session 时撤销，并删除 Cookie |
| `PUT /api/v1/auth/password` | Session + 同源 | 首次强制改密可省略当前密码；普通改密必须校验当前密码；成功后撤销该用户其他会话 |
| `POST /api/v1/admin/users` | 系统管理员 + 同源 | 创建 active 普通账号并一次性返回随机初始密码 |
| `GET /api/v1/admin/users` | 系统管理员 | 按 active/disabled 状态过滤并分页查询用户；不返回密码 |
| `POST /api/v1/admin/users/{id}/disable|enable` | 系统管理员 + 同源 | 禁用或启用普通账号 |
| `POST /api/v1/admin/users/{id}/reset-password` | 系统管理员 + 同源 | 撤销会话、强制首次改密并一次性返回新随机密码 |
| `GET /api/v1/projects` | Session | 分页返回当前用户可见项目 |
| `POST /api/v1/projects` | Session + 同源 | 创建默认私有项目 |
| `GET /api/v1/projects/{id}` | 项目成员 | 读取项目元数据 |
| `PATCH /api/v1/projects/{id}` | owner/editor + 同源 | 按 `version` 修改名称和描述 |
| `DELETE /api/v1/projects/{id}` | owner + 同源 | 归档完整项目并删除数据库记录，返回 204 |
| `GET /api/v1/projects/{id}/members` | 项目成员 | 返回永久 owner 和 editor/viewer 成员 |
| `POST /api/v1/projects/{id}/members` | `project.members.manage` + 同源 | 按用户名添加已有有效账号 |
| `PATCH /api/v1/projects/{id}/members/{user_id}` | `project.members.manage` + 同源 | 在 editor/viewer 间切换角色 |
| `DELETE /api/v1/projects/{id}/members/{user_id}` | `project.members.manage` + 同源 | 移除 editor/viewer，返回 204 |
| `GET /api/v1/projects/{id}/labels` | 项目成员 | 按顺序返回项目全部标签，不分页 |
| `POST /api/v1/projects/{id}/labels` | owner/editor + 同源 | 新增英文类别、可选中文描述和颜色 |
| `PATCH /api/v1/projects/{id}/labels/{label_id}` | owner/editor + 同源 | 按 `version` 修改名称、中文描述、颜色或启用状态 |
| `PUT /api/v1/projects/{id}/labels/order` | owner/editor + 同源 | 原子提交项目全部标签 ID 的新顺序 |
| `DELETE /api/v1/projects/{id}/labels/{label_id}` | owner/editor + 同源 | 删除未使用标签，返回 204 |
| `GET /api/v1/filesystem` | Session | 按重复的 `extensions` 参数浏览 `~` 内目录和受支持文件；支持当前目录 `search` 包含过滤 |
| `POST /api/v1/filesystem/directories` | Session + 同源 | 在 `~` 边界内新建目录 |
| `GET /api/v1/projects/{id}/videos` | 项目成员 | 分页读取视频、采样摘要和各视频最新任务；`page_size` 最大 999 |
| `PUT /api/v1/projects/{id}/videos/{video_id}/enabled` | owner/editor + 同源 | 按 `version` 修改视频整体启用状态 |
| `POST /api/v1/projects/{id}/videos/delete` | owner/editor + 同源 | 批量归档删除停用视频；逐项返回 `deleted` 与 `skipped`，启用视频不受影响 |
| `POST /api/v1/projects/{id}/imports/local/preview` | owner/editor + 同源 | 预览单文件或目录第一层视频，不递归 |
| `POST /api/v1/projects/{id}/imports/local` | owner/editor + 同源 | 批量创建本地复制任务，返回 202 |
| `POST /api/v1/projects/{id}/imports/remote/preview` | owner/editor + 同源 | 用 yt-dlp 解析 HTTP(S) 单视频或播放列表；空白标题回退为外部视频 ID |
| `POST /api/v1/projects/{id}/imports/remote` | owner/editor + 同源 | 为已选远程条目创建下载任务，返回 202 |
| `GET /api/v1/tasks` | Session | 分页返回当前用户可见项目的后台任务及项目上下文 |
| `GET /api/v1/projects/{id}/tasks` | 项目成员 | 分页读取持久任务、进度和错误 |
| `POST /api/v1/projects/{id}/tasks/{task_id}/cancel` | owner/editor + 同源 | 取消 queued 任务或请求 running 任务协作取消 |
| `POST /api/v1/projects/{id}/tasks/{task_id}/retry` | owner/editor + 同源 | 为 failed/canceled 任务创建新任务，返回 201 |
| `GET /api/v1/projects/{id}/videos/{video_id}/content` | 项目成员 | 播放原始视频，支持 HTTP Range |
| `GET /api/v1/projects/{id}/videos/{video_id}/download` | 项目成员 | 下载原始视频 |
| `GET /api/v1/projects/{id}/videos/{video_id}/thumbnail` | 项目成员 | 读取 Worker 生成/下载的 JPEG 缩略图 |
| `POST /api/v1/projects/{id}/sampling-plans` | owner/editor + 同源 | 为一个或多个 ready 视频创建或更新采样方案 |
| `POST /api/v1/projects/{id}/extractions` | owner/editor + 同源 | 按当前方案批量创建抽帧任务，返回 202 |
| `GET /api/v1/projects/{id}/videos/{video_id}/sampling-plan` | 项目成员 | 读取方案、预计/实际帧数、版本和帧修订号 |
| `GET /api/v1/projects/{id}/videos/{video_id}/frames` | 项目成员 | 分页读取帧；可用 `enabled=true/false` 过滤，`include_annotations=true` 批量附带轻量标注预览 |
| `GET /api/v1/projects/{id}/videos/{video_id}/frames/annotation-summary` | 项目成员 | 按帧序返回至少包含一个已保存标注框的帧 ID |
| `GET /api/v1/projects/{id}/videos/{video_id}/frames/{frame_id}/image` | 项目成员 | 读取受管 JPG/PNG 帧图片 |
| `PUT /api/v1/projects/{id}/videos/{video_id}/frames/enabled` | owner/editor + 同源 | 原子提交帧 ID 与启停状态的混合变更，校验 `frame_revision` |
| `GET /api/v1/projects/{id}/videos/{video_id}/frames/{frame_id}/annotations` | 项目成员 | 读取整帧矩形标注及 `annotation_revision` |
| `PUT /api/v1/projects/{id}/videos/{video_id}/frames/{frame_id}/annotations` | owner/editor + 同源 | 按修订号整体替换当前帧标注 |
| `GET /api/v1/models` | Session | 返回当前用户可见项目内的推理模型及入库状态 |
| `GET /api/v1/model-projects` | Session | 返回当前用户可见模型项目；普通项目按创建时间倒序，内置 `official_yolo11` 固定在末尾 |
| `POST /api/v1/model-projects` | Session + same-origin | 创建归档模型项目；训练类型拒绝手工创建 |
| `GET/PATCH/DELETE /api/v1/model-projects/{id}` | 项目可见；写入需对应原子权限 | 查看、版本化编辑或逻辑删除模型项目 |
| `GET/POST /api/v1/model-projects/{id}/members` | 项目成员；写入需 `project.members.manage` | 列出或添加 owner/editor/viewer 成员；内置项目不接受成员授权 |
| `PATCH/DELETE /api/v1/model-projects/{id}/members/{user_id}` | `project.members.manage` + 同源 | 切换 editor/viewer 或移除成员；内置项目拒绝写入 |
| `GET /api/v1/model-projects/{id}/models` | 项目成员 | 返回指定模型项目内模型 |
| `GET /api/v1/model-project-tags` | Session | 返回工作区模型项目标签候选 |
| `POST /api/v1/model-projects/{id}/models` | `task.execute` + same-origin | 创建 `.pt` 模型导入任务 |
| `GET/PATCH/DELETE /api/v1/models/{id}` | Session；写入需项目管理权 | 查看、编辑/移动或逻辑删除模型；详情响应对训练发布模型附带冻结的训练参数、`base_model_name`/`base_model_code` 与数据集摘要 |
| `GET /api/v1/models/{id}/download` | Session | 下载 ready 且路径通过受管目录校验的 `.pt` 模型 |
| `GET /api/v1/models/{id}/artifacts` | Session | 列出模型的 ONNX/TensorRT 转换产物；源模型或 TensorRT 构建环境变化时返回 `stale` |
| `POST /api/v1/models/{id}/artifacts` | `artifact.consume` + `task.execute` + 同源 | 创建 ONNX 或 TensorRT 转换任务；同一模型同一格式只保留一个当前产物 |
| `GET /api/v1/model-artifacts/{id}/download` | Session | 下载 ready 转换产物；TensorRT 响应携带仅限当前服务器使用的兼容性提示头 |
| `DELETE /api/v1/model-artifacts/{id}` | 模型项目管理员 + 同源 | 删除转换产物；活动任务正在使用时返回 409 |
| `GET /api/v1/models/{id}/inference/current` | Session | 恢复当前用户在该模型下唯一的未保存推理会话 |
| `POST /api/v1/models/{id}/inference` | `artifact.consume` + `task.execute` + 同源 | 以原始请求体流式上传图片或视频；图片最大 20 MB、视频最大 500 MB，视频返回后台任务会话 |
| `GET /api/v1/models/{id}/inference/saved` | Session | 列出模型项目内已保存的共享推理结果 |
| `GET /api/v1/model-inference/{id}` | 会话所有者；已保存结果对登录用户可读 | 查询图片/视频推理状态、参数和统计 |
| `POST /api/v1/model-inference/{id}/keepalive` | 会话所有者 + 同源 | 将未保存会话的 24 小时过期时间向后延长 |
| `POST /api/v1/model-inference/{id}/save` | 模型项目管理员 + 同源 | 保存成功结果并取消自动过期 |
| `DELETE /api/v1/model-inference/{id}` | 会话所有者 + 同源 | 清理会话；运行中的视频任务先请求取消，再由 Worker 安全移除文件 |
| `GET /api/v1/model-inference/{id}/files/{source|preview|result}` | 同推理结果读取权限 | 下载源文件、读取浏览器预览或下载检测结果 |
| `GET/POST /api/v1/model-projects/{id}/evaluation-datasets` | Session；写入需项目管理权与同源 | 列出测试集快照，或以原始请求体流式上传最大 1 GB 的 ZIP 并创建后台校验任务 |
| `DELETE /api/v1/evaluation-datasets/{id}` | 模型项目管理员 + 同源 | 逻辑删除未被活动评估使用的测试集；文件移入 `.deleted`，历史评估保留名称与哈希快照 |
| `GET/POST /api/v1/model-projects/{id}/evaluations` | Session；写入需项目管理权与同源 | 列出评估记录，或为一个具体模型、测试集和可用格式创建固定参数评估任务 |
| `GET /api/v1/model-evaluations/{id}` | Session | 返回冻结来源、总体/分类别指标和图表可用状态 |
| `POST /api/v1/model-evaluations/{id}/cancel` | 模型项目管理员 + 同源 | 请求取消排队中或运行中的评估 |
| `GET /api/v1/model-evaluations/{id}/plots/{confusion|pr-curve}` | Session | 读取受管目录内的混淆矩阵或 PR 曲线图片 |
| `GET /api/v1/hyperparameter-catalog` | Session | 返回 Detect v1 参数目录、类型、默认值和约束 |
| `POST /api/v1/hyperparameter-templates/validate-raw` | Session | 严格校验完整 RAW YAML；失败不返回可应用配置 |
| `GET/POST /api/v1/hyperparameter-templates` | Session；创建需模型项目 `project.update` 与同源 | 列出可见的系统/项目预设，或在指定模型项目中创建预设 |
| `GET/PATCH/DELETE /api/v1/hyperparameter-templates/{id}` | 可见项目成员；写入需 `project.update` 与同源 | 查看、按 `version` 编辑或逻辑删除项目模板；系统模板只读 |
| `GET /api/v1/training/capabilities` | Session | 返回 2 秒缓存的主机/GPU 实时显存、利用率、颜色级别和训练可用性 |
| `GET /api/v1/training/resources` | Session | 返回工作区 ready 数据集导出、含版本/完整参数/编辑权限的活动模板和 ready basemodel 候选 |
| `GET /api/v1/training-tasks/code-availability` | Session | 校验新任务不可变 code 的格式和可用性 |
| `GET/POST /api/v1/training-tasks` | Session；创建需同源 | 列出可见任务；创建草稿时同步创建仅创建者/管理员可见的训练模型项目 |
| `GET/PATCH /api/v1/training-tasks/{id}` | 项目 `task.read`；PATCH 需 `task.execute` 与同源 | 查看或修改任务；仅 draft 可按 `version` 修改 |
| `POST /api/v1/training-tasks/{id}/start|cancel` | `task.execute` + 同源 | 原子预检并冻结；多数据集任务先准备数据再排队训练 |
| `POST /api/v1/training-tasks/{id}/retry-preparation` | `task.execute` + 同源 | 仅为 `preparation_failed` 任务重建并排队数据准备记录 |
| `GET /api/v1/training-tasks/{id}/preparation-log` | Session | 返回当前数据准备子进程的去 ANSI 文本日志快照 |
| `POST /api/v1/training-tasks/{id}/retry-failed|resume-interrupted|derive` | `task.execute` + 同源 | 重试、恢复或派生新草稿 |
| `DELETE /api/v1/training-tasks/{id}` | `task.execute` + 同源 | 拒绝活动任务；归档运行目录并保留已发布模型 |
| `POST /api/v1/training-models/{id}/cancel|retry|resume` | `task.execute` + 同源 | 单模型取消、重试或恢复 |
| `POST /api/v1/training-models/{id}/derive|extend` | `task.execute` + 同源 | 派生或追加训练 |
| `DELETE /api/v1/training-models/{id}` | `task.execute` + 同源 | 活动模型拒绝；已发布模型要求显式确认 |
| `GET /api/v1/training-runs/{id}/metrics|log|pr-curve` | Session | epoch 指标、去 ANSI 且按回车覆盖语义还原的末尾日志快照和交互 P-R JSON；日志页在活动训练期间每 1.5 秒轮询 |
| `GET /api/v1/training-runs/{id}/log/download` | Session | 下载工作区内完整原始 `train.log`，不受页面末尾快照截断影响 |
| `GET /api/v1/me/x-anylabeling-server` | Session | 返回当前用户脱敏远程配置和 `null|true|false` 最近可用状态，不返回 API 密钥 |
| `PUT /api/v1/me/x-anylabeling-server` | Session + 同源 | 验证远程模型目录后保存 URL 和可选密钥 |
| `GET /api/v1/me/x-anylabeling-server/models` | Session | 实时刷新当前用户远程模型目录 |
| `GET/POST /api/v1/me/llm-configs` | Session；POST 需同源 | 列出或创建当前用户的大模型配置；密钥仅返回脱敏值 |
| `PATCH/DELETE /api/v1/me/llm-configs/{id}` | Session + 同源 | 修改或删除当前用户自己的大模型配置 |
| `POST /api/v1/me/llm-configs/{id}/test` | Session + 同源 | 使用对应协议发起最小模型请求并记录连接状态与响应时延 |
| `GET/PUT /api/v1/me/llm-configs/defaults` | Session；PUT 需同源 | 读取或保存当前用户的新配置默认高级参数 |
| `GET /api/v1/overview` | Session | 返回个人资源统计、主机/GPU 状态、个人训练任务和脱敏全局训练负载 |
| `POST /api/v1/projects/{id}/videos/{video_id}/frames/{frame_id}/auto-annotations` | owner/editor + 同源 | 同步运行单张推理并返回未保存草稿 |
| `POST /api/v1/projects/{id}/videos/{video_id}/auto-annotations` | owner/editor + 同源 | 创建批量自动标注任务，返回 202 |
| `POST /api/v1/projects/{id}/auto-annotations/batch` | owner/editor + 同源 | 按 `unannotated|all` 范围创建项目批量自动标注任务 |
| `POST /api/v1/projects/{id}/videos/batch-enabled-by-annotation` | owner/editor + 同源 | 按已保存标注批量更新帧启停，支持安全范围或确认覆盖 |
| `POST /api/v1/projects/{id}/dataset-exports` | owner/editor + 同源 | 按类别与源数据快照创建导出任务，返回 202 |
| `GET /api/v1/projects/{id}/dataset-exports` | 项目成员 | 分页读取未删除的数据集导出 |
| `GET /api/v1/projects/{id}/dataset-exports/{export_id}` | 项目成员 | 读取导出详情、绝对路径和清单 |
| `GET /api/v1/projects/{id}/dataset-exports/{export_id}/download` | 项目成员 | 流式下载 ready 产物 ZIP |
| `DELETE /api/v1/projects/{id}/dataset-exports/{export_id}` | owner/editor + 同源 | 逻辑删除非活动导出，返回 204 |

目录接口只接受相对 `~` 的路径，拒绝绝对路径、`..` 和解析后逃逸的符号链接，并从列表隐藏当前工作区。`GET /filesystem` 的 `extensions` 可重复传入，当前只接受服务端白名单中的视频扩展名和 `pt`；不传扩展名时只返回目录。返回条目的 `type` 为小写真实类型：目录是 `dir`，文件是去掉点号的扩展名。`search` 是不区分大小写的当前目录文件名包含匹配，在分页前执行且不递归。用户名使用 3–64 个 ASCII 字母、数字、`.`、`_` 或 `-`，密码长度为 12–256；成功初始化后口令立即失效。用户、项目和任务列表最大页大小 200，视频列表最大页大小 999，帧列表保持自身接口约束。当前错误响应仍使用 FastAPI `detail`，统一业务错误模型尚未实现。

认证 Cookie 为 HttpOnly、SameSite=Lax、Path=/；HTTPS 请求额外设置 Secure。服务端会话空闲 12 小时失效、创建 7 天后绝对失效。登录失败始终返回相同 401，不区分账号不存在、密码错误、状态或模式限制。普通账号由唯一系统管理员创建，创建/重置响应仅当次返回随机密码，数据库只保存 Argon2 哈希；首次改密前除 `/auth/me`、改密和退出外的业务请求返回 403 `password_change_required`。用户已通过初始密码建立会话，因此该次强制改密不重复要求当前密码；完成首次改密后的普通改密仍必须提交并校验当前密码。禁用账号立即撤销其会话；系统管理员不可禁用、重置或删除。

项目名称允许重复，资源主键和路由身份使用 UUID。项目列表与详情的 `categories` 仅包含按标签顺序排列的启用类别；停用类别仍保留在标签和数据集映射详情中。Video 响应额外返回不可变 `short_code`，用于界面显示和本地媒体/帧文件对应；短码不是路由参数，也不替代 UUID。无访问权的项目返回 404，避免泄露项目是否存在；已知成员权限不足返回 403；版本或资源状态冲突返回 409。创建者是永久 owner，不存在 owner 成员记录或所有权转移接口。访问来源优先判定创建者，因此系统管理员自建项目返回 `access.role=owner`、`access.source=owner`；管理员访问他人项目时在 multi/single 模式下都隐式获得全部权限，返回 `access.role=null`、`access.source=system_admin`，但不写入成员表。前端将后一来源简写为“管理员”。

项目响应的 `access.permissions` 使用固定集合：`project.read`、`project.update`、`project.members.manage`、`project.delete`、`artifact.read`、`artifact.download`、`artifact.consume`、`task.read`、`task.execute`。owner 和系统管理员拥有全部权限；editor 缺少成员管理和项目删除；viewer 只有项目/产物/任务读取及产物下载。该映射同时用于数据集项目、模型项目及其子资源，不提供自定义角色或权限表。

当前角色能力：

| 能力 | owner | editor | viewer |
| --- | --- | --- | --- |
| 查看项目与成员 | 是 | 是 | 是 |
| 修改项目名称、描述 | 是 | 是 | 否 |
| 添加、改角色、移除成员 | 是 | 否 | 否 |
| 归档删除项目 | 是 | 否 | 否 |
| 浏览 `~` 内文件/目录、新建目录 | 是 | 是 | 是 |
| 查看、播放、下载项目原始视频 | 是 | 是 | 是 |
| 查看项目任务 | 是 | 是 | 是 |
| 预览/导入本地或远程视频 | 是 | 是 | 否 |
| 取消/重试视频导入任务 | 是 | 是 | 否 |
| 启停视频整体下游参与状态 | 是 | 是 | 否 |
| 归档删除停用视频 | 是 | 是 | 否 |
| 查看和下载采样帧 | 是 | 是 | 是 |
| 配置采样方案、创建抽帧任务 | 是 | 是 | 否 |
| 批量启停采样帧 | 是 | 是 | 否 |
| 查看项目标签 | 是 | 是 | 是 |
| 新增、修改、排序、启停和删除未使用标签 | 是 | 是 | 否 |
| 读取已有矩形标注 | 是 | 是 | 是 |
| 进入在线标注工作台并保存标注 | 是 | 是 | 否 |
| 运行单张或批量自动标注 | 是 | 是 | 否 |
| 创建模型项目 | 是 | 是 | 是 |
| 编辑、导入和执行模型项目任务 | 是 | 是 | 否 |
| 查看和下载已有模型/转换/训练/推理/评估产物 | 是 | 是 | 是 |
| 查看和下载已有数据集导出 | 是 | 是 | 是 |
| 创建和逻辑删除数据集导出 | 是 | 是 | 否 |

viewer 可查看、播放和下载授权范围内的原始视频、采样帧、数据集导出、模型、转换产物、训练结果、已保存推理结果和评估结果；不能修改项目/标签/标注/帧状态，不能创建或删除产物，也不能发起自动标注、转换、推理、评估或训练。为简化交互，视频列表的“标注”入口对 viewer 禁用；读取标注 API 保留，以支持只读展示。

项目删除要求 owner 权限，且任意 queued/running 项目任务都会返回 409。服务端先在项目目录写入包含项目、成员、标签、视频、采样方案、帧、标注、任务和数据集导出全部当前持久字段的 `project_metadata.json`，再将目录原子移动到 `.deleted/projects/<project UUID>/project/`，最后级联删除数据库记录；提交失败时尝试把目录移回。该快照仅对应生成时 schema，不承诺未来兼容，当前也不提供加载或恢复接口。

创建导出要求训练集比例位于 `[0, 1]`、类别快照完整且映射连续，并至少启用一个类别；同一项目已有 queued/running 导出时返回 409。任务活动期间，参与视频的启停、帧启停、重抽帧和手动/自动标注写入返回 409，读取不受影响。列表和详情返回 `total_videos/train_videos/val_videos`，总数仅为训练与验证视频之和，不含排除或停用视频；新生成的 manifest 同步写入这三项，旧 manifest 由视频 ID 数组派生响应。导出详情只在 ready 后包含工作区绝对路径与 `manifest`；下载不生成持久 ZIP，删除将产物移动到 `.deleted/projects/<project UUID>/exports/` 并从普通列表隐藏。

标签名称由服务端转为小写并压缩空白，只允许英文字母、数字、空格、连字符和下划线；项目内不区分大小写唯一。`description_zh` 为最长 64 字符的可选显示说明，不作为模型类别或提示词。批量排序请求必须恰好包含项目当前全部标签 ID，否则返回 422。标签重名、过期版本以及删除已被标注引用的标签返回 409。内部标签身份使用 UUID，排序变化不修改标注关联。

能力接口在后端进程启动时探测一次。`gpu` 返回设备序号、名称和总显存；`pytorch_cuda` 以及 `features.manual_annotation/yolo_auto_annotation/model_training` 分别返回 `available` 和可空 `reason`。本地 YOLO 能力要求 PyTorch CUDA 与 Ultralytics；探测失败只降级本地功能，不影响应用启动或外部 X-AnyLabeling 使用。

矩形标注坐标使用原图像素整数，必须位于图片边界内，单帧最多 10000 项；响应顺序同时是稳定对象编号和图层顺序。客户端只在切换帧、点击其他缩略图、启动批量任务或关闭标注工作台时提交整帧草稿；`annotation_revision` 过期返回 409。浏览器意外刷新、崩溃或断电不会后台频繁保存，页面只通过 `beforeunload` 警告未保存修改。帧列表默认不返回标注，标注工作台显式使用 `include_annotations=true` 一次加载缩略图所需的框坐标和标签 ID。

筛帧工作台先在浏览器维护启停草稿，保存时只提交与打开页面时基准不同的帧。`PUT .../frames/enabled` 请求体为 `{"changes":[{"frame_id":"...","enabled":false}],"frame_revision":4}`；同一请求中的帧 ID 必须唯一且都属于目标视频，服务端在一个事务内更新全部状态并只递增一次帧修订号。版本过期返回 409且不进行部分写入。标注帧摘要只返回存在至少一个已保存标注框的帧 ID；前端用该集合结合当前启停草稿实时计算标注帧启用/停用统计和“按标注启停”结果。批量按标注启停的 `scope=unscreened-only` 只处理有标注且 `frame_revision <= 1` 的视频；`scope=all` 可覆盖已筛帧视频，但存在 `frame_revision > 1` 的有标注视频时必须提交 `confirm_all=true`。无标注视频在两种范围中都进入 `rejected(code=no_annotations)`，其帧启停不变。

单张自动标注在 API 同步线程池运行，只返回可编辑草稿，不修改当前标注。请求用 `source=local|xanylabeling|online`、`model_id` 和可空 `remote_task_id` 标识来源；本地模型使用进程内互斥锁，X-AnyLabeling 与在线视觉大模型读取当前用户配置。X-AnyLabeling 配置初始可用状态为 `null`；设置验证或模型目录刷新成功写入 `true`，目录、推理错误或超时写入 `false`。在线来源使用内置目标检测矩形框提示词，分别按 OpenAI-compatible 或 Anthropic 原生消息格式发送图片，不引入 Agent 框架。`categories` 接受项目英文标签或临时英文类别，`All` 表示使用模型可提供的全部类别；只有实际检出的缺失类别会加入项目标签。项目批量接口的 `scope=unannotated` 忽略已有标注视频且强制 `overwrite=false`，`scope=all` 可包含已有标注视频；前端在混合范围和覆盖场景分别确认。批量接口拒绝停用视频，并把 Worker 开始执行时启用的帧作为处理范围；任务只保存来源和模型选择，不保存服务器 URL、API 密钥或图片。`overwrite=false` 追加模型框，`overwrite=true` 覆盖整帧已有框。活动远程任务期间修改对应用户配置返回 409。

大模型配置创建时 `version` 从 1 开始；更新使用乐观版本。API Key 写入前由工作区凭据密钥加密，配置响应不返回明文，仅提供 `has_api_key` 和类似 `sk-test-******abcd` 的 `masked_api_key`。编辑请求省略或留空 `api_key` 表示保留旧密钥。连接测试不依赖 `/models` 列表能力，而是按配置的 API 类型向指定模型发送最小请求，因此兼容不实现模型目录接口的本地和在线服务。

模型项目默认私有，创建者是永久 owner，可将有效普通账号授权为 editor/viewer；系统管理员自建项目仍以 owner 身份呈现，访问他人项目时无需成员授权即可管理。内置“YOLO11目标检测官方模型”对所有 active 普通账号提供隐式 viewer 权限，不接受成员授权，也不能作为普通账号的自动标注、转换、推理、评估或训练输入；管理员可编辑该项目并导入、编辑或删除其中的具体模型，但不能删除整个内置项目。training 项目只随训练草稿创建并继承关联模型项目的访问来源，不能手工创建。普通项目和模型删除从查询隐藏记录并归档受管文件；可见范围内的 ready 模型和已有产物允许下载。

系统超参数模板全局可读且不可修改；用户模板归属指定模型项目，按项目权限可见，只有 `project.update` 可创建、派生、编辑或删除，viewer 不可将其用于训练。模板响应包含 `model_project_id`、`version/updated_at`；PATCH 的旧版本返回 409。RAW 接口只接受经严格校验的单文档顶层 mapping。

训练草稿的附加参数覆盖格式固定为 `{"version":1,"set":{...},"remove":[...]}`；核心参数使用独立可空字段。模型未选择显式模板时严格继承任务最终超参；选择显式模板时只叠加模型覆盖。启动接口读取模板最新版本并冻结最终参数快照，此后模板编辑不影响已提交、运行中或已完成任务。

创建训练草稿时同步建立唯一关联的 training 模型项目；任务、日志、指标和发布结果均继承该项目访问。owner/editor/管理员可执行生命周期操作，viewer 只读，非成员得到 404。保存草稿和启动训练都会验证目标项目的执行权限，以及每个数据集导出、basemodel 和非系统模板所属项目的 `artifact.consume` 权限。任务 code 是不可变全局业务标识而非主键，UUID 继续承担路由和外键身份。

三种模式分别为 `single_model`、`single_device_serial` 和 `custom_sequence`。一个模型只属于一个 GPU lane，同卡严格串行、不同 GPU 可并行，不支持单 GPU 多模型并行或一个模型使用多 GPU。GPU 高显存只产生红/橙风险提示，不阻止选择；本系统已有 active run 会由数据库和调度器强制排队。

任务默认数据集支持 `single` 或 `multi`，模型可 `inherit`、`single` 或 `multi`。多数据集配置版本固定为 1，包含非空的 ready 导出 UUID 列表和按目标索引排序的非空 `target_classes`；来源类别按导出 manifest 中的精确名称映射。允许只选择一个导出使用多数据集映射；同名来源类别自动归入同一目标类别，类别同名但大小写不同视为不同类别。启动边界会重新验证配置、导出状态、标签索引和磁盘空间，客户端校验不构成信任边界。

多数据集不会修改原导出目录。准备进程为图片创建硬链接、复制并改写每个 YOLO TXT 的第一列，保持原 train/val/test 划分并发布独立 `data.yaml`。准备期间任务/模型状态为 `preparing`，失败为 `preparation_failed`；详情响应附带 preparation 进度、阶段、已处理/总数、时间和安全错误。准备成功后才创建 initial run 和参与 GPU lane 调度。

生命周期 action 可携带最长 128 字符的 `Idempotency-Key`。重试生成新 run；恢复只允许 failed/canceled 且有有效 last.pt；派生生成新 task/model 且请求 DTO 不接受 dataset/basemodel；追加训练只允许成功模型并创建新单模型草稿。成功模型重试还必须提交 `confirm_replace=true`，新训练失败不会修改当前发布模型。

全局任务接口按项目可见性过滤，按任务创建时间倒序返回。每项在普通任务字段之外包含 `project_id`、`project_name` 和 `can_manage`；viewer 的 `can_manage=false`。分页响应的 `latest_terminal_at` 在全部可见任务中计算，不受当前页限制，用于浏览器任务中心判断 succeeded、failed 或 canceled 任务是否未读。取消和重试仍使用项目级写接口，权限检查不在全局查询中复制。

视频列表每项包含 `enabled`、`has_annotations`、可空 `sampling` 和可空 `latest_task`。`has_annotations` 由当前页视频 ID 一次关联查询得出，不逐视频请求或持久化冗余计数。采样摘要包含 `updated_at`，前端据此判断失败任务是否已被后续资源修改覆盖。各视频最新任务由服务端一次批量查询取得。`PUT .../enabled` 请求体为 `{"enabled": false, "version": 2}`；版本过期返回 409，viewer 返回 403。视频停用只控制未来自动标注和导出的参与资格，不禁止播放、采样配置、抽帧、筛帧或手动标注。

单个项目最多 999 个视频。批量导入容量不足时，剩余容量内条目进入 `accepted`，超出部分进入 `rejected` 并给出容量原因；前端按钮禁用不是最终约束，数据库触发器仍会拒绝并发产生的第 1000 条记录。

采样方案支持：

- `target_frames`：参数 `minimum` 为 10–100，`maximum` 为 100–300，且前者小于后者；默认 50/200。2 分钟及以下取 minimum，2–10 分钟线性增长，10 分钟及以上取 maximum，源视频帧数不足时保留全部帧。
- `frame_interval`：参数 `interval` 为 1–100000，从第 0 帧开始每 N 帧取一帧。
- `time_interval`：参数 `seconds` 和 `frames` 均为 1–10，换算成确定的帧间隔。
- 输出为 `jpg` 时质量为 1–31、默认 2；输出为 `png` 时压缩级别为 0–9、默认 6。

`POST .../sampling-plans` 的 `overwrite_level` 为 `none`、`configured` 或 `sampled`，默认 `none`；级别不足时对应视频进入 `rejected`。更新方案只增加方案版本，不立即删除旧帧。`POST .../extractions` 的 `overwrite_level` 为 `none`、`light` 或 `destructive`，默认 `none`：无标注且未筛帧的已有帧至少要求 `light`，存在标注或 `frame_revision > 1` 任意一项至少要求 `destructive`。服务端按实时状态重新校验，批量拒绝项包含稳定 `code` 和可读 `reason`。

抽帧成功才更新 `applied_version`、`generation` 和帧记录；活动任务和未配置方案以逐项 rejected 返回。`extract_frames` queued/running 期间，采样配置、帧启停和标注替换写接口返回 409，读取不受影响。帧批量启停要求客户端提交当前 `frame_revision`，过期值返回 409，一次请求最多传 999 个帧 ID；不传 `frame_ids` 表示操作该视频全部帧。

本地导入可提交单文件或目录预览返回的路径，目录只扫描第一层。远程导入只接受 HTTP/HTTPS，允许局域网 HTTP；播放列表解析后由用户选择条目再提交。批量响应分别列出 `accepted`、`skipped` 和 `rejected`。本地文件在 Worker 中计算完整 SHA-256，远程文件以 yt-dlp extractor + 原始 ID 在项目内判重；重复任务以成功但 skipped 的结果结束，不新增重复 Video。

## 遗留接口范围

遗留 Flask 应用有 46 个路由声明，功能分为以下资源族。

### 项目与设置

- `GET/POST /api/projects`
- `GET/DELETE /api/projects/{project_id}`
- `GET/PUT /api/projects/{project_id}/settings`
- `POST /api/projects/read`
- `POST /api/projects/preview`
- `POST /api/projects/check-directory`
- `POST /api/directories/check-project`

### 服务端文件浏览

- `POST /api/directories/db-files`
- `POST /api/directories/video-files`
- `GET /api/directories`
- `GET /api/system/home`
- `GET /api/system/roots`
- `POST /api/directories/conf-files`
- `POST /api/directories/txt-files`

这些接口暴露服务端路径模型，仅适合受信任单机环境。新 API 不提供无边界的绝对路径浏览。

### 视频

- 项目视频列表。
- 从播放列表、单 URL、单本地文件或本地目录导入。
- 批量或单视频下载。
- 更新启用状态、备注。
- 查询状态、播放媒体和读取缩略图。

遗留兼容接口同时存在 `/is-used` 和 `/enabled`。

### 帧

- 帧列表、指纹、图片和标注。
- 读取/保存帧启停位图。
- 计算采样与启动抽帧。

### 任务、分组、导出与配置

- 视频级和项目级 SSE。
- 保存分组并生成组目录。
- 创建数据集导出。
- 预览和加载项目配置。

当前前端只消费项目级 SSE。遗留 API 文档漏记帧 fingerprint，并把实际 `groups_conf.yaml` 写成 JSON；因此不能用作新 API 的兼容规范。

### 图片分支

延期图片分支另有图片列表、标签映射、文件读取、目录导入、批量启停、标签过滤和去重接口。它们只进入后续需求设计。

## 新 API 契约原则

### 资源模型

第一阶段使用 `/api/v1`，围绕以下资源设计：

- setup
- auth sessions、registrations、users
- capabilities、filesystem
- projects
- project members
- videos
- frames
- sampling plans
- annotation batches
- exports
- tasks

FastAPI OpenAPI 是唯一契约来源。前端类型从规范生成或在 CI 中校验；资源使用稳定 ID 和项目作用域，不用文件路径作为资源身份。

当前初始化客户端为少量手写 TypeScript 类型；OpenAPI 类型生成在业务 API 增长后引入。

### 响应与错误

- 成功响应直接返回资源或分页结构，不为了统一包装增加多层 `data`。
- 错误统一包含 `code`、`message`、`details`、`request_id`。
- HTTP 状态码表达请求结果；业务错误不统一伪装为 200。
- 批量操作返回任务批次和逐项结果，明确 accepted、skipped、rejected，禁止静默部分成功。
- 时间使用 ISO 8601 UTC；枚举和单位写入 API 规范。

### 分页、过滤与排序

- 视频、帧、任务和导出列表使用 `page`、`page_size`、`total` 分页；视频页的 999 表示读取单项目全部视频。
- 过滤、排序字段使用白名单，并由 API 规范记录。
- 大批量帧分析由服务端聚合或任务完成，不允许前端逐帧请求形成瀑布。

### 长任务

下载、文件复制、抽帧、标注批次物化/同步和导出不在请求生命周期内完成：

1. 客户端提交命令。
2. 服务端验证资源状态并创建持久任务。
3. 返回 `202 Accepted` 和任务资源位置。
4. 客户端查询任务，或订阅从持久状态派生的事件。
5. 最终结果通过任务和目标资源共同确认。

任务创建支持幂等键。事件包含任务 ID、项目 ID、状态、进度和时间；SSE 断线后客户端重新查询任务列表，不建立额外持久事件队列。

### 媒体与文件

- 上传、导入、播放、缩略图和帧图片只引用受控资源 ID；外部浏览只接受 `~` 相对路径。
- 服务端路径必须在存储层解析，拒绝 `..`、符号链接逃逸和根目录外绝对路径。
- 媒体播放由 API 支持 HTTP Range；后续如性能不足再交给反向代理。
- 所有已认证用户可浏览服务启动用户的 `~`；解析符号链接后仍需位于该目录，工作区本身从浏览列表隐藏。

### 状态并发

- 修改资源时使用版本号、ETag 或等效乐观并发控制，避免两个页面互相覆盖帧筛选或分组。
- 服务端验证视频状态转移，客户端显示状态但不决定合法性。
- 任务启动接口对相同资源和参数必须幂等或明确返回冲突任务。

## 认证与授权

运行模式：

- 默认 `multi`，内置账号密码认证。
- `single` 只允许初始化管理员使用用户名和密码登录。
- 两种模式共用 User、Session 和后续项目成员数据；模式切换不修改业务数据。

所有模式要求：

- 每个受保护请求都从服务端 Session 解析用户身份；单用户模式不会注入匿名身份。
- 项目列表和项目子资源按成员权限过滤。
- 查看、编辑、执行任务、导出和管理成员是可区分权限。
- SSE/WebSocket 与文件下载执行同样的授权检查。
- 关键写操作记录操作者和请求追踪信息。
- 浏览器使用 HttpOnly Session Cookie，写请求执行同源/CSRF 检查。
- 系统不提供开放注册；唯一系统管理员创建普通账号并发放一次性随机初始密码。
- 当前可信局域网部署不提供浏览器 Token、无认证、IP/CIDR 或可信代理模式。

项目角色为 owner、editor、viewer。系统管理员在所有运行模式下隐式拥有全部数据集与模型项目权限，不需要 owner 授权，也不写入成员表。

## 规范与兼容性

- 新 API 由 FastAPI 生成机器可读 OpenAPI，前端类型/客户端和文档从同一契约生成或在 CI 中校验。
- 遗留 `/api` 路由没有兼容承诺；需要迁移时通过适配工具，而不是永久携带重复接口。
- 破坏性变更需要版本策略和迁移说明。
- 首批只维护 `/api/v1`；破坏性契约变化进入新版本，不为遗留 Flask API 提供兼容层。
