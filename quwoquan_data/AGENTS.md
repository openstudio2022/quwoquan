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
- `.qwq_output/` 只允许可删除重建的运行产物、部署快照、证据与缓存；禁止把 `control_plane/prompts/templates/schema/specs/policies/reference` 等可复用真相源放入 output。Python venv 只是由仓内 `requirements.txt` 临时重建的 disposable cache，不是可复用测试环境、工程配置或发布资产；任何任务都不得要求该缓存预先存在。
- Python bytecode、pytest cache 只能写入 `.qwq_output/env/repo/local/**` 或测试隔离临时根；解释器工具缓存只能写入仓外的用户缓存目录（默认 `~/.cache/quwoquan/python-envs`），两者都不得进入 `quwoquan_data/**`。所有 Make/gate/pytest 入口必须以解释器 `-B` 启动、显式重定向 pytest cache，并在执行后运行 Data layout gate。

## 内容供给端到端闭环

- 数据工程必须同时覆盖两条供给线：内容稿件线（article/image/moment/video/route 等 post package）与实体/标签/素材治理线（entity homepage、tagRefs、semantic mentions、review ledger、asset safety）。
- 标准链路为 `0.plan -> sources -> 1.download -> 2.quality -> 3.compose -> 4.draft -> 5.review -> publish -> ship -> service importer`。
- 一个执行只有一个 `.qwq_output/data/tasks/<executionId>/` 工作包；失败以新 sequence + `retryOf` 重试，禁止静态 task、batch 双寻址或原地篡改输入。
- 正文只能由 Agent 基于 `writing_pack.json` 和 `prompt.md` 创作并写回，`generator=agent` 是交付面硬门；脚本不得拼正文。
- 图片、事实、来源权利、实体主页、tagRefs、semantic mentions、人审账本和发布态必须可追溯；不可追溯即不可发布。
- 内容载体按底稿形态路由：图片集合为主且文字只是标题/配文的是 `image` 图片作品；图文混合编排且源图随正文共同构成底稿的是 `article`；entity homepage 正文只允许 `encyclopedia-primary` 三百科闭集（Wikipedia、百度百科公开词条、今日头条百科）。官网、政府/文旅门户、OTA、Wikivoyage、360、Wikidata、OSM 与百科搜索不得投影为主页底稿或主证据。
- canonical `publish/` 只含通过 review 的自治 creators/entities/posts/media objects，及其引用的 `tags/<tagRef>/_definition.json` consumer snapshot；control-plane taxonomy 与 creator profile 仍是唯一可编辑静态输入，禁止复制整棵 taxonomy 或未引用标签进入 publish；事务写入前后使用内容摘要校验，不维护永久 freeze、迁移索引或兼容状态；
  release 唯一在 `.qwq_output/data/releases/{releaseId}`，环境证据唯一在
  `.qwq_output/env/{env}/runs/data-release/{releaseId}/{runId}`。`ship`/importer
  只读 canonical + desired state，禁止 retired path fallback 或 v1/v2 dual-read。
- 数据产物最终必须能被 App 发现、搜索、消费和互动，并通过行为反馈进入推荐、运营指标和下一轮内容优化。

## 质量与 Review

- Review 必须先判定证据是否充足，再判定 prompt/template 是否失配，最后才判定创作执行问题；不同归因回退到不同阶段。
- 禁止百科罗列、机械收尾、模板化小标题、来源痕迹、不可商用素材、平台水印、未经改写长句复现。
- 内容角度、实体类型、tagRefs、manifest、asset id、source paths、发布账本必须一致；不一致先修契约或数据，不用代码绕过。
- 数据工程同样要补 `local_contract` schema/静态/CLI/模块、`api_integration` importer/真实存储或环境采样、`user_acceptance` 用户消费链路证据。

## 数据工程七角色准出

- **资深软件工程**：CLI-first、无孤立脚本、复用 `core`、失败可恢复、测试可重复。
- **资深数据工程师**：DAG/stage result/gate report/typed recovery/sample bundle/importer 幂等完整。
- **数据质量 QA**：schema、事实回溯、图片安全、去重、golden set、rubric、dirty scan 有证据。
- **法务法律专家**：来源权利、授权快照、blocked 来源、反抄袭、长句复现、人脸/肖像/商用风险可审计。
- **消费者视角**：标题兑现、信息密度、图文节奏、可读性、feed/search/detail 可消费。
- **内容运营专家**：SLO/KPI、人审 SLA、发布节奏、反馈修复、内容供给优化闭环。
- **无人值守自动化**：object queue、fanout、budget、hook-check、repair report、失败回退能自动闭环。

缺任一角色证据，先补 `specs/tests/gates` 或 repair stage，不要把离线文件生成当成完成。

## 典型触发与 E2E

- 用户说“内容生产、抓取、冷启动、实体主页、标签治理、图片安全、ship、导入 gamma/beta/prod”时，默认加载本文件和 `quwoquan-data-content` skill。
- 数据任务不能停在离线文件层；必须说明如何进入 service importer、App 发现/搜索/消费、行为反馈和推荐/运营分析。
- 若涉及环境导入或发布，必须同步加载 `quwoquan_ops/AGENTS.md` 并收集 stackctl 证据。

## 推荐验证

- 优先使用 `python3 quwoquan_data/scripts/cli.py ...` 执行对应流程
- 启动托管工作流前先跑一键环境门：`python3 quwoquan_data/scripts/cli.py task preflight`；它会检查 `cursor_sdk`、CV/OCR 依赖、仓外 `$HOME/.config/quwoquan/cursor_api_key`（显式 `QWQ_CURSOR_API_KEY_FILE` 仅用于受控替换）和网络可达性。
- 数据工程校验优先跑 `python3 quwoquan_data/scripts/cli.py verify all`
- 若触及 CLI 入口约束，再补跑 `python3 quwoquan_data/scripts/verify/verify_cli_first.py`
- 多角色准出清单：`python3 quwoquan_data/scripts/cli.py verify data-role-gate`
- 两省最终准出：`python3 quwoquan_data/scripts/cli.py verify two-province-coverage-release --release <releaseId>`
- 发布、采样、导入或环境数据变化后，补跑对应 `ship`、服务侧 importer 测试和与环境职责匹配的 `stackctl verify --env <env> --kind all --profile integration|release`。
