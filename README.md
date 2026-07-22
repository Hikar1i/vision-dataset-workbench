# Vision Dataset Workbench

面向视觉数据集生产流程的工作台。项目将以遗留的单机视频数据集管理工具为业务参考，先重构视频导入、下载、采样、抽帧、筛选、分组和导出主链路，再建设多用户权限、图片数据集、在线标注和模型自动标注能力。

## 当前状态

项目处于重构前的分析与设计阶段，当前仓库尚无可运行的应用代码。遗留项目已完成代码、文档、数据库和提交历史梳理；分析结论用于定义重构边界，不代表本仓库已经实现对应功能。

首批实现范围：

- 视频数据集项目管理。
- 远程和本地视频导入。
- 可恢复的下载、采样和抽帧任务。
- 帧筛选、视频分组与数据集导出。
- 统一 API、版本化数据库迁移和安全文件边界。

后续范围：

- 多用户、项目成员、角色和权限。
- 图片数据集导入、标签映射、标签过滤和相似图去重。
- 在线标注、模型管理与自动标注。

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
