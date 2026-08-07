# Vision Dataset Workbench

面向视觉数据集生产流程的多人工作台。项目以遗留单机工具为业务参考，已重构视频导入、采样、筛帧、权限、在线矩形标注和 YOLO Detect 训练主链路，并支持本地 YOLO、外部 X-AnyLabeling-Server 及用户配置的在线视觉大模型自动标注。

## 当前状态

项目已完成遗留系统分析、总体重构设计、首次初始化、账号认证、项目成员权限，以及视频导入、采样、抽帧、筛帧、项目标签和在线矩形标注主链路。FastAPI 提供受管媒体、帧、标签、标注、推理模型与运行能力 API，独立 Worker 负责复制、yt-dlp 下载、FFmpeg 抽帧、模型入库和批量自动标注，Vue 3 提供统一工作台界面。

已实现：

- 一次性终端口令保护的首次初始化。
- 限制在服务启动用户 `~` 内的目录浏览和新建目录。
- 原子创建 `.vision-dataset-workbench`、初始管理员和工作区定位文件。
- 默认多用户、可切换单用户的账号密码认证。
- 注册申请、管理员审批、账号禁用/启用和离线管理员密码重置。
- 12 小时空闲/7 天绝对有效期的 HttpOnly 服务端会话，以及浏览器同源写保护。
- 默认私有的视频项目、永久所有者以及 editor/viewer 成员权限。
- 项目元数据乐观并发控制，以及多用户隔离和单用户管理员兼容访问。
- 项目级英文类别、可选中文描述、颜色、0 起始映射顺序和启停管理；owner/editor 可写，viewer 只读。
- 认证后的 `~` 文件浏览、新建目录和一级视频目录扫描；工作区目录不会暴露在浏览结果中。
- 本地视频完整 SHA-256 去重、远程视频 extractor/原始 ID 项目内去重，以及保留原容器扩展名的受管存储。
- SQLite 持久复制/下载任务、租约恢复、取消、重试、进度与错误记录。
- 独立 Python Worker；复制和下载分别全局并发 2、同类型每用户并发 1。
- HTTP/HTTPS 单视频与播放列表预览，及可选实例级 yt-dlp 代理和 Netscape Cookie 文件。
- owner/editor 可导入，viewer 可查看、播放和下载原始视频但不能导入或管理任务。
- 每个视频持久保存版本化采样方案，支持目标帧数、固定帧间隔和时间间隔三种模式。
- 目标帧数模式按视频时长计算可预测结果：2 分钟及以下取短视频目标，2–10 分钟线性增长，10 分钟及以上取长视频上限。
- 抽帧任务默认全局并发 2、每用户并发 1；使用临时目录和原子替换，失败或取消不会破坏上一代帧。
- JPG/PNG 输出、稳定帧记录、帧分页浏览和带版本冲突检测的批量启停。
- viewer 可查看和下载采样帧；owner/editor 可配置、重采样和筛选帧，覆盖已有方案或帧时按实际标注/筛帧风险分级确认。
- owner/editor 可从视频列表进入全屏在线标注工作台；viewer 的标注入口禁用。
- 基于 Konva 的原图坐标矩形框编辑，支持绘制、选中、移动、缩放、撤销/重做、画布平移缩放、十字线、快捷键、对象列表和帧缩略图导航。
- 标注仅在切换帧或关闭工作台时保存；修订号冲突返回 409，意外刷新或关闭仅警告未保存修改。
- 所有认证用户可创建归档模型项目；创建者和系统管理员可编辑、导入 `.pt` YOLO、移动或逻辑删除模型，其他用户只读。历史“临时模型项目”保留为只读兼容资源。
- 所有认证用户可创建不可变的 YOLO Detect 超参数模板，并从已有模板派生；核心参数与扩展参数支持表单/RAW YAML 双向编辑，RAW 仅在语法、键、类型及取值全部通过服务端校验后才覆盖表单。
- 全局训练任务支持单模型、单 GPU 串行和多 GPU 自定义序列；同卡严格单模型、跨卡并行，GPU 实时显存以绿/橙/红提示但不强制阻止选择。
- 每个训练模型在独立 Python 子进程运行，Worker 按持久 GPU lane 调度；任务详情展示进度、PID、主机快照、日志，以及带联动指针和缩放的 loss、学习率、precision、recall、mAP 与 P-R 曲线。
- 成功模型自动发布到训练类型模型项目；提供重试、恢复中断、派生、追加训练、取消和逻辑删除，并区分各操作的数据集、basemodel、超参数和 checkpoint 语义。
- 标注页可按模型项目选择本地 YOLO，或按用户配置 X-AnyLabeling-Server 地址和可选 API 密钥；单张返回可复核草稿，批量任务支持追加或覆盖已有框。
- 每个用户可维护多个 OpenAI-compatible 或 Anthropic 大模型配置，支持本机、局域网及在线 Base URL；API Key 加密落库、只脱敏回显，连接测试记录状态和时延。
- 批量自动标注在混合选择时先确认处理范围；覆盖已有标注必须显式解锁风险设置。“按标注启停”忽略无标注视频，覆盖已有筛帧结果前需要 3 秒二次确认。
- 自动标注支持项目标签、`All` 全类别及临时英文提示词；只为实际检出的新类别创建项目标签。
- 单项目最多 999 个视频，数据库处理并发容量竞争；owner/editor 可按版本启停视频的批量自动标注与导出参与状态。
- 高密度视频工作台提供项目轨道、紧凑媒体台账、派生业务状态标签、批量风险统计、当前页全选以及 25/50/100/200/全部分页。
- 启动时检测 NVIDIA GPU、PyTorch CUDA 和 Ultralytics；缺少 GPU 或依赖时保持启动并提示本地 YOLO 功能降级。
- uv 可选 `gpu` 依赖组仅包含 PyTorch、torchvision 和 Ultralytics；X-AnyLabeling-Server 和在线视觉大模型均通过 HTTP 解耦，不引入 Agent 或本地大模型框架。
- Python 3.12/FastAPI 与 Vue 3/TypeScript/Vite 项目骨架。

下一阶段：

- 按功能域和最终 RBAC 方案重构全局资源权限。
- 真实 YOLO 数据集/权重的 GPU 操作矩阵与长时稳定性验收。
- 在线标注的真实模型与大批量性能冒烟、审计记录和操作细节迭代。
- 按实际交互需求评估任务事件推送；当前任务抽屉使用轮询。

## 开发启动

```bash
cd backend
uv sync --python 3.12 --dev
uv run uvicorn vision_dataset_workbench.main:app --app-dir src --reload --port 38000

# 另一个终端
cd backend
uv run python -m vision_dataset_workbench.worker

# 另一个终端
cd frontend
npm install
npm run dev
```

GPU 服务器将后端安装命令改为 `uv sync --python 3.12 --dev --extra gpu`；无 GPU 实例不安装该 extra。

浏览器打开 `http://127.0.0.1:35173`，输入后端终端显示的一次性口令，选择工作区父目录并创建首个管理员；初始化后使用该账号登录。前端开发服务器默认把 `/api` 代理到 `http://127.0.0.1:38000`。视频处理还要求系统可执行 `ffmpeg` 和 `ffprobe`；API 与 Worker 必须指向同一工作区。

验证命令见[测试策略](docs/06-testing-strategy.md)，配置和首次启动细节见[环境与启动](docs/08-environments.md)。

## 文档

- [项目背景与目标](docs/01-project-background.md)
- [架构](docs/02-architecture.md)
- [数据库](docs/03-database.md)
- [API](docs/04-api.md)
- [代码规范](docs/05-code-style.md)
- [测试策略](docs/06-testing-strategy.md)
- [部署](docs/07-deployment.md)
- [环境与启动](docs/08-environments.md)
- [已知问题](docs/09-known-issues.md)

## 本地 AI 工作区

AI 生成的调查、设计、计划和临时产物存放在 `.ai-local/`，并通过 `.git/info/exclude` 排除。用户提供的 `.ai-local/references/` 只读；长期项目文档只存放在根目录 `README.md` 和 `docs/`。
