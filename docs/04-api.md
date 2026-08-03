# API

状态：`/api/v1` 初始化、认证、用户、项目、项目标签、运行能力、文件浏览、视频导入、任务、采样方案、帧、矩形标注、推理模型、自动标注和数据集导出接口已实现。

## 当前接口

| 方法与路径 | 认证 | 用途 |
| --- | --- | --- |
| `GET /api/v1/health` | 无 | 进程存活检查，返回 `{"status":"ok"}` |
| `GET /api/v1/capabilities` | Session | 返回缓存的 GPU、PyTorch CUDA、ONNX CUDA 与功能能力 |
| `GET /api/v1/setup/status` | 无 | 返回工作区是否已初始化 |
| `GET /api/v1/setup/directories` | `X-Setup-Token` | 分页浏览启动用户 `~` 内目录 |
| `POST /api/v1/setup/directories` | `X-Setup-Token` | 在受控父目录中新建目录 |
| `POST /api/v1/setup/initialize` | `X-Setup-Token` | 创建工作区和首个管理员 |
| `GET /api/v1/auth/status` | 无 | 返回 `multi/single` 运行模式和注册开关 |
| `POST /api/v1/auth/login` | 同源 | 登录并设置 `vdw_session` Cookie |
| `GET /api/v1/auth/me` | Session | 返回当前安全用户字段 |
| `POST /api/v1/auth/logout` | 同源 | 存在 Session 时撤销，并删除 Cookie |
| `PUT /api/v1/auth/password` | Session + 同源 | 校验当前密码、改密并撤销该用户其他会话 |
| `POST /api/v1/registrations` | 同源；注册已开放 | 创建 `pending` 用户 |
| `GET /api/v1/admin/users` | 系统管理员 | 按状态过滤并分页查询用户 |
| `POST /api/v1/admin/users/{id}/{action}` | 系统管理员 + 同源 | approve、reject、disable 或 enable |
| `GET /api/v1/projects` | Session | 分页返回当前用户可见项目 |
| `POST /api/v1/projects` | Session + 同源 | 创建默认私有项目 |
| `GET /api/v1/projects/{id}` | 项目成员 | 读取项目元数据 |
| `PATCH /api/v1/projects/{id}` | owner/editor + 同源 | 按 `version` 修改名称和描述 |
| `DELETE /api/v1/projects/{id}` | owner + 同源 | 归档完整项目并删除数据库记录，返回 204 |
| `GET /api/v1/projects/{id}/members` | 项目成员 | 返回永久 owner 和 editor/viewer 成员 |
| `POST /api/v1/projects/{id}/members` | owner + 同源 | 按用户名添加已有有效账号 |
| `PATCH /api/v1/projects/{id}/members/{user_id}` | owner + 同源 | 在 editor/viewer 间切换角色 |
| `DELETE /api/v1/projects/{id}/members/{user_id}` | owner + 同源 | 移除 editor/viewer，返回 204 |
| `GET /api/v1/projects/{id}/labels` | 项目成员 | 按顺序返回项目全部标签，不分页 |
| `POST /api/v1/projects/{id}/labels` | owner/editor + 同源 | 新增英文类别、可选中文描述和颜色 |
| `PATCH /api/v1/projects/{id}/labels/{label_id}` | owner/editor + 同源 | 按 `version` 修改名称、中文描述、颜色或启用状态 |
| `PUT /api/v1/projects/{id}/labels/order` | owner/editor + 同源 | 原子提交项目全部标签 ID 的新顺序 |
| `DELETE /api/v1/projects/{id}/labels/{label_id}` | owner/editor + 同源 | 删除未使用标签，返回 204 |
| `GET /api/v1/filesystem` | Session | 按 `kind=directory/video/model` 浏览 `~` 内目录和受支持文件 |
| `POST /api/v1/filesystem/directories` | Session + 同源 | 在 `~` 边界内新建目录 |
| `GET /api/v1/projects/{id}/videos` | 项目成员 | 分页读取视频、采样摘要和各视频最新任务；`page_size` 最大 999 |
| `PUT /api/v1/projects/{id}/videos/{video_id}/enabled` | owner/editor + 同源 | 按 `version` 修改视频整体启用状态 |
| `POST /api/v1/projects/{id}/imports/local/preview` | owner/editor + 同源 | 预览单文件或目录第一层视频，不递归 |
| `POST /api/v1/projects/{id}/imports/local` | owner/editor + 同源 | 批量创建本地复制任务，返回 202 |
| `POST /api/v1/projects/{id}/imports/remote/preview` | owner/editor + 同源 | 用 yt-dlp 解析 HTTP(S) 单视频或播放列表 |
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
| `GET /api/v1/models` | Session | 返回工作区内推理模型及入库状态 |
| `POST /api/v1/projects/{id}/models` | 系统管理员 + 项目访问 + 同源 | 登记 `~` 内 YOLO 文件或 GroundingDINO 目录并创建入库任务 |
| `POST /api/v1/projects/{id}/videos/{video_id}/frames/{frame_id}/auto-annotations` | owner/editor + 同源 | 同步运行单张推理并返回未保存草稿 |
| `POST /api/v1/projects/{id}/videos/{video_id}/auto-annotations` | owner/editor + 同源 | 创建批量自动标注任务，返回 202 |
| `POST /api/v1/projects/{id}/dataset-exports` | owner/editor + 同源 | 按类别与源数据快照创建导出任务，返回 202 |
| `GET /api/v1/projects/{id}/dataset-exports` | 项目成员 | 分页读取未删除的数据集导出 |
| `GET /api/v1/projects/{id}/dataset-exports/{export_id}` | 项目成员 | 读取导出详情、绝对路径和清单 |
| `GET /api/v1/projects/{id}/dataset-exports/{export_id}/download` | 项目成员 | 流式下载 ready 产物 ZIP |
| `DELETE /api/v1/projects/{id}/dataset-exports/{export_id}` | owner/editor + 同源 | 逻辑删除非活动导出，返回 204 |

目录接口只接受相对 `~` 的路径，拒绝绝对路径、`..` 和解析后逃逸的符号链接，并从列表隐藏当前工作区。用户名使用 3–64 个 ASCII 字母、数字、`.`、`_` 或 `-`，密码长度为 12–256；成功初始化后口令立即失效。用户、项目和任务列表最大页大小 200，视频列表最大页大小 999，帧列表保持自身接口约束。当前错误响应仍使用 FastAPI `detail`，统一业务错误模型尚未实现。

认证 Cookie 为 HttpOnly、SameSite=Lax、Path=/；HTTPS 请求额外设置 Secure。服务端会话空闲 12 小时失效、创建 7 天后绝对失效。登录失败始终返回相同 401，不区分账号不存在、密码错误、状态或模式限制。禁用账号立即撤销其会话，且不能禁用最后一个有效系统管理员。

项目名称允许重复，资源主键和路由身份使用 UUID。Video 响应额外返回不可变 `short_code`，用于界面显示和本地媒体/帧文件对应；短码不是路由参数，也不替代 UUID。无访问权的项目返回 404，避免泄露项目是否存在；viewer 修改返回 403；项目元数据版本不匹配返回 409。项目列表默认每页 50，最大 200。创建者是永久 owner，不存在 owner 成员记录或所有权转移接口。多用户模式下系统管理员不自动获得项目访问权；单用户模式下管理员运行时获得所有项目的 owner 等效权限，但不会改写成员数据。

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
| 查看和下载采样帧 | 是 | 是 | 是 |
| 配置采样方案、创建抽帧任务 | 是 | 是 | 否 |
| 批量启停采样帧 | 是 | 是 | 否 |
| 查看项目标签 | 是 | 是 | 是 |
| 新增、修改、排序、启停和删除未使用标签 | 是 | 是 | 否 |
| 读取已有矩形标注 | 是 | 是 | 是 |
| 进入在线标注工作台并保存标注 | 是 | 是 | 否 |
| 运行单张或批量自动标注 | 是 | 是 | 否 |
| 登记全局推理模型 | 仅系统管理员 | 仅系统管理员 | 否 |
| 查看和下载已有数据集导出 | 是 | 是 | 是 |
| 创建和逻辑删除数据集导出 | 是 | 是 | 否 |

viewer 已可查看、播放和下载原始视频，查看任务、采样方案、采样帧图片、标注数据和数据集导出，并可下载 ready 产物；不能添加或导入视频、启停视频整体、改变采样策略、重新采样、启停帧、写入标注、创建或删除导出。为简化交互，视频列表的“标注”入口对 viewer 禁用；读取标注 API 保留，以支持只读展示。

项目删除要求 owner 权限，且任意 queued/running 项目任务都会返回 409。服务端先在项目目录写入包含项目、成员、标签、视频、采样方案、帧、标注、任务和数据集导出全部当前持久字段的 `project_metadata.json`，再将目录原子移动到 `.deleted/projects/<project UUID>/project/`，最后级联删除数据库记录；提交失败时尝试把目录移回。该快照仅对应生成时 schema，不承诺未来兼容，当前也不提供加载或恢复接口。

创建导出要求训练集比例位于 `[0, 1]`、类别快照完整且映射连续，并至少启用一个类别；同一项目已有 queued/running 导出时返回 409。任务活动期间，参与视频的启停、帧启停、重抽帧和手动/自动标注写入返回 409，读取不受影响。导出详情只在 ready 后包含工作区绝对路径与 `manifest`；下载不生成持久 ZIP，删除将产物移动到 `.deleted/projects/<project UUID>/exports/` 并从普通列表隐藏。

标签名称由服务端转为小写并压缩空白，只允许英文字母、数字、空格、连字符和下划线；项目内不区分大小写唯一。`description_zh` 为最长 64 字符的可选显示说明，不作为 YOLO 类别或 DINO 提示词。批量排序请求必须恰好包含项目当前全部标签 ID，否则返回 422。标签重名、过期版本以及删除已被标注引用的标签返回 409。内部标签身份使用 UUID，排序变化不修改标注关联。

能力接口在后端进程启动时探测一次。`gpu` 返回设备序号、名称和总显存；`pytorch_cuda`、`onnx_cuda` 以及 `features.manual_annotation/yolo_auto_annotation/grounding_dino_auto_annotation/model_training` 分别返回 `available` 和可空 `reason`。YOLO 能力要求 PyTorch CUDA 与 Ultralytics；GroundingDINO 能力要求 PyTorch CUDA 与 Transformers。探测失败只降级功能，不影响应用启动；具体模型是否已入库不属于该接口。

矩形标注坐标使用原图像素整数，必须位于图片边界内，单帧最多 10000 项；响应顺序同时是稳定对象编号和图层顺序。客户端只在切换帧、点击其他缩略图、启动批量任务或关闭标注工作台时提交整帧草稿；`annotation_revision` 过期返回 409。浏览器意外刷新、崩溃或断电不会后台频繁保存，页面只通过 `beforeunload` 警告未保存修改。帧列表默认不返回标注，标注工作台显式使用 `include_annotations=true` 一次加载缩略图所需的框坐标和标签 ID。

筛帧工作台先在浏览器维护启停草稿，保存时只提交与打开页面时基准不同的帧。`PUT .../frames/enabled` 请求体为 `{"changes":[{"frame_id":"...","enabled":false}],"frame_revision":4}`；同一请求中的帧 ID 必须唯一且都属于目标视频，服务端在一个事务内更新全部状态并只递增一次帧修订号。版本过期返回 409且不进行部分写入。标注帧摘要只返回存在至少一个已保存标注框的帧 ID；前端用该集合结合当前启停草稿实时计算标注帧启用/停用统计和“按标注启停”结果。

单张自动标注在 API 同步线程池运行，只返回可编辑草稿，不修改当前标注；同一模型的进程内推理使用互斥锁，避免并发复用模型对象。`categories` 接受项目英文标签或临时英文类别，`All` 表示使用模型可提供的全部类别；只有实际检出的缺失类别会加入项目标签。批量接口拒绝停用视频，并把 Worker 开始执行时启用的帧作为处理范围；`overwrite=false` 追加模型框，`overwrite=true` 覆盖整帧已有框，两种模式都不改变帧启停状态。批量任务活动期间该视频标注写接口返回 409，前端进入只读并轮询任务状态；失败或取消保留此前已成功提交的帧。

模型入库只允许系统管理员发起。YOLO 接受模型文件，GroundingDINO 接受本地 Transformers 模型目录；Worker 复制到 `models/<model UUID>/` 后将状态置为 `ready`。`ready` 只表示受管副本已发布，权重格式与运行库兼容性在首次推理时最终验证。`import_model` 和 `auto_annotate` 任务不开放通用重试接口，用户需重新发起以确认参数和范围。

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
- 注册默认关闭；启用后新账号需管理员批准。
- 当前可信局域网部署不提供浏览器 Token、无认证、IP/CIDR 或可信代理模式。

项目角色为 owner、editor、viewer。系统管理员在多用户模式下不自动读取全部项目内容；单用户模式临时授予工作区管理员全部项目访问权。

## 规范与兼容性

- 新 API 由 FastAPI 生成机器可读 OpenAPI，前端类型/客户端和文档从同一契约生成或在 CI 中校验。
- 遗留 `/api` 路由没有兼容承诺；需要迁移时通过适配工具，而不是永久携带重复接口。
- 破坏性变更需要版本策略和迁移说明。
- 首批只维护 `/api/v1`；破坏性契约变化进入新版本，不为遗留 Flask API 提供兼容层。
