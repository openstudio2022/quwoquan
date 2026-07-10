# quwoquan_data Codex Guide

在 `quwoquan_data/` 工作时，除仓库根 `AGENTS.md` 外，先阅读仓库根 `.cursor/rules/` 与数据工程入口：

1. `quwoquan_data/README.md`
2. `.cursor/rules/01-arch-constraints.mdc` 中关于 `quwoquan_data` 的 CLI-first 约束

## 数据工程硬约束

- 一律遵守 `CLI prepare -> Agent semantic -> CLI validate + gate` 三段式。
- 新能力优先进入 `python3 quwoquan_data/scripts/cli.py <command>`，不要新增可直接运行的业务入口脚本。
- schema、blueprint、metadata、tag taxonomy、内容契约先行，再写下载/生产/发布逻辑。
- 内容生成以真实性、可追溯性和阶段结果为核心；不要用拍脑袋补全替代证据链。
- 新脚本归位到现有领域目录，禁止在仓库根创建平铺 `scripts/`。
- 当前阶段未上线：旧模板拼文、区域硬编码、版本化 publish 路径、孤立脚本、不可追溯素材、弱事实证据一律直接清理，不做兼容。

## 内容供给端到端闭环

- 数据工程必须同时覆盖两条供给线：内容稿件线（article/image/moment/video/route 等 post package）与实体/标签/素材治理线（entity homepage、tagRefs、semantic mentions、review ledger、asset safety）。
- 标准链路为 `plan -> download -> produce compose-brief -> Agent semantic -> produce review/materialize -> media check-images -> verify -> ship -> service importer`。
- 每个 stage 必须落 stage result、gate report、repair report；失败按 `fallbackStage` 回退，禁止无证据 `--resume` 或原地反复重写。
- 正文只能由 Agent 基于 `writing_pack.json` 和 `prompt.md` 创作并写回，`generator=agent` 是交付面硬门；脚本不得拼正文。
- 图片、事实、来源权利、实体主页、tagRefs、semantic mentions、人审账本和发布态必须可追溯；不可追溯即不可发布。
- 内容载体按底稿形态路由：图片集合为主且文字只是标题/配文的是 `image` 图片作品；图文混合编排且源图随正文共同构成底稿的是 `article`；Wiki/百科/官方/政府/文旅等介绍实体本身的是 entity homepage。禁止把 homepage/article/image 三路来源混用，文章源图也按底稿证据链一稿一用。
- `ship` 后必须能形成环境 sample bundle，并可由服务侧 importer 幂等灌库；数据工程任务不能停在离线文件生成。
- 数据产物最终必须能被 App 发现、搜索、消费和互动，并通过行为反馈进入推荐、运营指标和下一轮内容优化。

## 质量与 Review

- Review 必须先判定证据是否充足，再判定模板/SOP 是否失配，最后才判定创作执行问题；不同归因回退到不同阶段。
- 禁止百科罗列、机械收尾、模板化小标题、来源痕迹、不可商用素材、平台水印、未经改写长句复现。
- 内容角度、实体类型、tagRefs、manifest、asset id、source paths、发布账本必须一致；不一致先修契约或数据，不用代码绕过。
- 数据工程同样要补 `local_contract` schema/静态/CLI/模块、`api_integration` importer/真实存储或环境采样、`user_acceptance` 用户消费链路证据。

## 数据工程七角色准出

- **资深软件工程**：CLI-first、无孤立脚本、复用 `_common`、失败可恢复、测试可重复。
- **资深数据工程师**：DAG/stage result/gate report/repair/fallback/sample bundle/importer 幂等完整。
- **数据质量 QA**：schema、事实回溯、图片安全、去重、golden set、rubric、dirty scan 有证据。
- **法务法律专家**：来源权利、授权快照、blocked 来源、反抄袭、长句复现、人脸/肖像/商用风险可审计。
- **消费者视角**：标题兑现、信息密度、图文节奏、可读性、feed/search/detail 可消费。
- **内容运营专家**：SLO/KPI、人审 SLA、发布节奏、反馈修复、内容供给优化闭环。
- **无人值守自动化**：object queue、fanout、budget、hook-check、repair report、失败回退能自动闭环。

缺任一角色证据，先补 `docs/tests/gates` 或 repair stage，不要把离线文件生成当成完成。

## 典型触发与 E2E

- 用户说“内容生产、抓取、冷启动、实体主页、标签治理、图片安全、ship、导入 gamma/beta/prod”时，默认加载本文件和 `quwoquan-data-content` skill。
- 数据任务不能停在离线文件层；必须说明如何进入 service importer、App 发现/搜索/消费、行为反馈和推荐/运营分析。
- 若涉及环境导入或发布，必须同步加载 `quwoquan_ops/AGENTS.md` 并收集 stackctl 证据。

## 推荐验证

- 优先使用 `python3 quwoquan_data/scripts/cli.py ...` 执行对应流程
- 启动托管工作流前先跑一键环境门：`python3 quwoquan_data/scripts/cli.py env ready`；它会准备 `quwoquan_data/.venv`，检查 `cursor_sdk`、CV/OCR 依赖、`CURSOR_API_KEY` 和网络可达性。
- 数据工程校验优先跑 `bash quwoquan_data/scripts/verify/verify_quwoquan_data.sh`
- 若触及 CLI 入口约束，再补跑 `python3 quwoquan_data/scripts/verify/verify_cli_first.py`
- 多角色准出清单：`python3 quwoquan_data/scripts/cli.py verify data-role-gate`
- 商用放量证据门：`python3 quwoquan_data/scripts/cli.py verify scale-readiness --task <task> --batch <batch> --daily-target 10000`
- 发布、采样、导入或环境数据变化后，补跑对应 `ship`、服务侧 importer 测试和 `stackctl verify --env <env> --kind all --tier all`。
