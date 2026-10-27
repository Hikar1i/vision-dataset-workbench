# AI Agent 部署执行流程

本文供目标机器上的 AI Agent 阅读并按步骤执行。用户只需提供项目目录或源码、必要的离线镜像素材，再使用 [README 中的简短提示词](../README.md#agent-辅助部署)。完整部署约束和验收要求均在本文中，无需把本文复制到对话。

## 执行目标与边界

在目标机器完成 Vision Dataset Workbench 部署、初始化、登录验收和结果交接。你可以执行必要的源码构建、镜像加载、项目内配置及启动命令；先检测环境再自动选 CPU 或 NVIDIA GPU，遇到可处理的问题继续推进。以下需要用户明确授权后才能执行：安装/升级宿主显卡驱动、更改 Docker 全局配置（含 daemon/镜像源/runtime）、删除旧卷或其他旧数据。不要绕过此边界，也不要删除已有实例解决冲突。仅在确有需要且获得授权后修改全局配置；若被阻断，给出具体原因及所需授权。

按以下顺序推进，记录环境检查、选型、启动、初始化、登录和业务验收的实际结果。遇到需要用户输入或授权的步骤，仅暂停依赖该输入的操作，并说明具体原因。默认动态检测 CPU / NVIDIA GPU，用户无需选择两套提示词。

## 一、识别素材、宿主与既有部署

1. 找到提供的源码包/仓库、镜像归档和部署文档。先阅读 README、project-docs/07-deployment.md、Dockerfile、compose.yaml、compose.gpu.yaml、.env.example；如有 AGENTS/本地覆盖规则也须遵守。以收到版本的实际代码、锁文件和能力检测为准，不编造已验收平台。源码包应核对归档 SHA256，在新的空目录解压，再核对 SHA256SUMS；不覆盖现有源码/.env。镜像归档也核对独立交付的校验值。未提供可信校验时明确记录完整性尚未确认。

2. 检测宿主 OS/版本、CPU 架构、磁盘/内存、当前 shell、Docker CLI/daemon 可连接性、Docker Compose v2 版本、Docker daemon OS/架构与 context 是否指向远端。Windows/macOS 使用 Docker Desktop 的 Linux containers；daemon 必须报告 linux。记录检查的实际输出摘要，不能只根据宿主 OS 或有无 nvidia-smi 选择 GPU。远端 context 的目录挂载/GPU/端口属于 daemon 主机，不是本地 CLI 主机，须核实后操作。

3. 只读盘点 Compose 项目、容器、端口、镜像和卷，识别该项目的现有实例、project name、数据卷、CPU/GPU 选型及初始化状态。不要输出含秘密的完整 docker inspect、compose config 或环境变量。已有 .env 只改必要配置，不覆盖真实密钥。禁止 down -v、volume prune、删除工作区、重新初始化已初始化数据库、自动重置旧用户密码。

4. 默认新部署使用独立且固定的 Compose 项目名（例如 vdw-user，先确认未被占用），所有 build/up/ps/logs/exec/stop 命令都保持相同 -p 名称及配置文件。已有实例继续使用其原项目名与 home 卷；不要误把新卷当成已有卷。若用户意图为升级，先核对同版本 API/Worker/web，等待/处理活动任务并停止整栈、备份整个 home 卷及密钥，核实备份可读后才启动会自动迁移数据库的新版本。操作已有业务任务或计划外停机需先与用户确认。不能兼容 schema 的回滚必须恢复备份。

## 二、自动检测并选择运行方式

5. macOS Docker Desktop、仅 AMD/Intel GPU、无 NVIDIA GPU 或无法暴露 GPU 的环境，自动选择 CPU。ARM64 未验收，AMD GPU 不受此 GPU 方案支持；不得宣称已测或默认用 CUDA/ROCm/Metal。核对目标 daemon 与镜像实际 OS/架构，不静默强制 amd64 仿真为“原生支持”；ARM 只能报告现场实际构建/运行结果及未验收限制，缺少兼容依赖时解释阻断。

6. 对可能支持 NVIDIA 的 Linux 或 Windows WSL2 Docker 环境，检查宿主驱动/GPU、Docker GPU 透传。对匹配架构且可信的可用镜像运行带 --gpus all 的临时探针（--rm；禁止挂业务卷），实际执行 nvidia-smi；需要联网拉探针镜像时说明来源，离线则使用已交付 GPU 镜像。宿主 nvidia-smi 成功不等于容器可用。根据此版本 GPU 依赖和 07 文档检查驱动兼容性；当前文档给出的完整 TensorRT 前提是兼容的 R580+，不能仅凭版本号保证一切可用，宿主无需单独安装 CUDA Toolkit。

7. 驱动/透传/架构兼容时自动选 GPU 配置，API 和 Worker 均须使用 GPU 镜像和同样的 GPU 设备视图。进入实际应用镜像检测 PyTorch CUDA 可用性、设备枚举及一次小张量 CUDA 运算（同步确认执行成功），启动后再检查实际系统能力。不要把 pip 安装成功或 nvidia-smi 成功当作本地模型能力全部可用。TensorRT/ONNX 等功能须逐项记录可用性和原因，缺模型时明确尚未完成真实模型业务验收。

8. 若 GPU 无法使用，明确区分驱动不足、设备未透传、镜像架构、依赖加载、显存等实际错误，并选择 CPU 降级；不要无限重试或偷偷装驱动/改全局 runtime。GPU 已启动时先确认无活动任务、停止本项目整栈，再用 CPU 配置及同一 home 卷启动，保留已有数据。仅可选 TensorRT 能力失败而核心 CUDA 功能可用时，保留 GPU 并如实标注不可用项；不能宣称完整 GPU 通过。离线缺少 CPU 镜像时报告缺失素材和所需架构，等待补充，不能声称已经降级成功。

## 三、配置、构建或离线加载、启动

9. 配置 .env：VDW_BIND_ADDRESS 默认 127.0.0.1；仅用户需要远程访问时使用适当的监听地址并说明防火墙；VDW_PORT 默认 8080，先检测冲突再选空闲端口；VDW_IMPORTS 指向用户实际来源目录（不存在时仅在新部署目录创建空 imports）。Windows 使用 D:/datasets 一类路径，值含空格时正确引用。不要将整个宿主 HOME 或敏感目录挂入容器，不更改宿主 HOME 环境变量。

10. 持久化 /data/home（容器 HOME）到 home 命名卷，API/Worker 共用；导入来源只读挂载到 /data/home/imports，界面使用 ~/imports。工作区父目录选择可写的 /data/home，不选只读 imports；应用创建 .vision-dataset-workbench。检查 UID/GID 10001:10001 的读写权限、Docker Desktop 目录共享；不要用 chmod 777 解决权限。VDW_CREDENTIAL_ENCRYPTION_KEY 未配置时由应用在工作区生成密钥，备份时连同 config/credential.key；不要替换旧密钥造成旧凭据不可读。YTDLP_PROXY/YTDLP_COOKIE_FILE 等按需配置，任何真实秘密不入源码、镜像、公共日志或报告。

11. 完整源码部署：必须有 Dockerfile/deploy/backend 源码及 uv.lock/迁移/frontend 源码及 package-lock/配置，只有 compose 文件不够。允许按选型执行构建，需可访问基础镜像、Python/npm 依赖源。CPU：docker compose -p <项目名> -f compose.yaml build api web；GPU 加 -f compose.gpu.yaml。构建失败保留具体脱敏错误，不更改全局镜像源；网络阻断时优先采用匹配架构离线镜像。

12. 离线镜像部署：docker load -i <归档>，确认实际镜像 ID、标签、linux OS/架构与来源；CPU 需 vision-dataset-workbench:cpu 和 :web，GPU 需 :gpu 和 :web。若同标签被其他项目使用，加载前先识别，保留旧镜像 ID/恢复标签方案，避免破坏其他项目重建所需镜像。离线不构建、不拉取缺失依赖。所有方式启动均使用 docker compose -p <项目名> -f compose.yaml [GPU 时另加 -f compose.gpu.yaml] up -d --no-build --pull never --wait。方括号是说明，不要原样复制进命令。

13. 确认 api/worker/web 都正常，记录实际使用配置、项目名和卷名；GPU 后续每条 Compose 操作继续携带两份 -f。API/web 有健康检查，Worker 无独立健康接口，需结合状态、日志和任务进展验收。不得只启动前端/API 就报告任务系统可用。

## 四、初始化管理员并完成登录

14. 先访问 /api/v1/setup/status。只有 initialized=false 的新实例才从 API 日志安全取得一次性 setup token，用初始化向导选择 /data/home、创建首个管理员。setup token 是首次设置口令，不是用户登录密码，初始化成功即失效；没有默认管理员账号或密码。管理员用户名遵守实际校验，当前为 3–64 位字母/数字/下划线/点/连字符；密码长度 12–256。用户名按用户意愿设置；密码由用户通过私密交互设置，或安全随机生成且每次唯一，绝不硬编码模板密码、复用验收密码或 SSH 密码。

15. 允许通过实际页面或当前版本 API 完成初始化；若用脚本，凭据仅经交互输入/受限内存传入，禁止出现在 shell 命令行参数、history、截图、公共执行日志或源码中。不要把包含 token 的完整 API 日志复制到公开报告。初始化后必须用实际管理员用户名和密码登录验证；令牌和 Cookie 不得外泄。已有实例直接用用户安全提供的现有凭据登录，缺凭据时请求私密提供，不重建账号/卷，不自行重置密码。

## 五、分别验收健康、能力和业务

16. 记录实际访问 URL（远程用户使用可达主机名/IP，0.0.0.0 不是访问地址）、Compose 状态与 /api/v1/health 返回。health 只是进程存活，不代表初始化、GPU、数据库任务均可用。另确认 setup/status 的 initialized=true、实际登录成功，并在登录态访问 /api/v1/capabilities 或系统运行能力页面，逐项报告 GPU/功能状态及原因。

17. GPU 选型时，在 API 和 Worker 中分别执行应用镜像 CUDA 探测，确认一致；CPU 选型只检查相应能力及降级原因，无需安装或导入 GPU 依赖。GPU 不可用按上面的降级规则处理。使用隔离的验收项目/少量非敏感样本验证一次导入、Worker 任务完成、页面能查看；没有样本时用临时合成图，验收产物不要入交付源码。GPU 如提供可信模型/样本则执行最小真实模型任务；不擅自下载或运行陌生 .pt。能力探测通过但未做模型任务的部分应标“未验收”，不要承诺训练/转换全通过。

18. CPU 可用范围：视频/图像导入、抽帧、筛选、手工标注、远程自动标注、数据集导出、模型与测试集管理、历史结果查看和下载。CPU 不执行本地模型自动标注、训练、转换、在线推理或评估。远程标注/在线视觉模型需要用户自备可达服务及凭据，不随部署自动提供；容器内 127.0.0.1 指容器自身。离线不会自动获得模型权重或互联网服务。

## 六、必须交付结果与实际登录凭据

19. 给出脱敏部署结果：成功/部分成功/阻断，OS/arch、daemon/context、素材与校验、CPU/GPU 选择依据及降级原因、镜像 ID、服务/健康/初始化/能力/业务验收各项结果、访问地址、实际卷名及导入映射、持久化/备份位置、同项目同配置的停止/启动/日志命令、未验收项和下一步。不得把未执行的检查写成通过。

20. 必须完成实际登录凭据的安全交接，不能只说“管理员已创建”。单独通过用户认可的私密渠道/密码管理器交付访问 URL、实际管理员用户名、实际初始密码及已验证登录情况；用户自行输入并保存密码时，确认其已持有并成功登录，也视为完成私密交接。公共报告只写交接状态，不含密码、setup token、Cookie、SSH 凭据。若没有安全渠道，请用户选择私密输入/接收方式；此前仅标记“凭据交接待完成”，不能宣布整项部署完成。不要将秘密保存在仓库、打包素材、公共报告或截图。用户收到初始密码后提醒修改并安全保存。

## 附录：交付者可选的素材准备

直接通过 Git 获取完整项目即可按上述流程部署，目标机无需运行 `package_source.py`，也不需要为此安装 Python。只有需要向他人传递当前工作树的精简源码归档时，交付者才使用本附录。

### 可选附件 `package_source.py` 的职责

该脚本只负责可重复执行的文件约束与完整性记录：按固定路径和扩展名白名单选取源码，拒绝符号链接和被选中的非普通文件，拒绝覆盖已有输出，以独占创建方式生成归档，失败时清理自己新建的输出，并生成逐文件及归档 SHA256。这些约束由代码执行，避免每次让 Agent 临时拼接打包命令。

它不负责环境判断、CPU/GPU 选择、容器启动、密码初始化或部署成功判定；这些流程由 Agent 依据本文和系统实际响应完成。若仅通过 Git 分发项目，可以完全跳过该附件。文件白名单不能识别源码内误写的秘密，SHA256 也不能证明来源可信。

### 生成源码归档与离线镜像

在仓库根目录用 Python 3.11+ 执行（读取当前工作树，包含尚未提交的白名单源码）：

```bash
python3 deploy/package_source.py /absolute/path/to/delivery/vdw-source.tar.gz
python3 deploy/package_source.py --selfcheck
```

Windows 可将 `python3` 换为 `py -3`，输出使用实际 Windows 路径。输出文件不能已存在。脚本仅使用标准库，产出源码 `.tar.gz`、同名 `.tar.gz.sha256`；归档根目录含逐文件 `SHA256SUMS`。传输前后核对整体 SHA256，解压后核对清单。Linux 可使用 `sha256sum -c vdw-source.tar.gz.sha256` 和在解压目录执行 `sha256sum -c SHA256SUMS`；macOS 可用 `shasum -a 256 -c`，Windows 用 `Get-FileHash -Algorithm SHA256` 比较清单值。校验值应从可信交付渠道取得，单纯哈希不证明来源可信。

白名单包含 Docker/Compose/env 示例、部署脚本、后端 Python 源码/锁文件/迁移、前端源码/资源/锁文件/构建配置、README 与 project-docs Markdown。排除 Git、本地 AI 材料、真实 `.env`、依赖环境、测试文件/结果、构建输出、数据库和业务目录。白名单内发现符号链接或特殊文件会拒绝打包；不会跟随仓库的 `docs` 链接。新增构建所需的扩展名或配置文件后，应同步检查脚本白名单。不要把业务数据、凭据或验收结果放进源码白名单目录；白名单不是内容级密钥扫描器。打包期间暂停修改交付源码，以免得到跨时刻内容；打包不要求 Git 干净，但没有替代构建验收。

离线交付另需在联网、匹配目标架构的构建机准备镜像。以下命令交由主实施/构建 Agent 执行，按实际选型运行：

```bash
# CPU
docker compose build api web
docker save -o vdw-cpu-images.tar vision-dataset-workbench:cpu vision-dataset-workbench:web
# NVIDIA GPU（选 GPU 时执行）
docker compose -f compose.yaml -f compose.gpu.yaml build api web
docker save -o vdw-gpu-images.tar vision-dataset-workbench:gpu vision-dataset-workbench:web
```

GPU 离线目标若需要失败后降级，也必须预先携带 CPU 镜像归档；只有 GPU 镜像无法离线变出 CPU 镜像。镜像包另行生成、核对 SHA256，记录每个镜像的 ID、OS/架构和构建来源。至少同时交付 `compose.yaml`、`compose.gpu.yaml`、`.env.example`、本文和部署文档；可直接附完整源码包。镜像不包含管理员账号、业务数据或模型权重，离线环境需自行提供模型与外部服务。源码包本身不是离线依赖包，不能保证断网重建镜像。
