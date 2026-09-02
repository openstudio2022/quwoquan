# quwoquan_data Codex Guide

在 `quwoquan_data/` 工作时，除仓库根 `AGENTS.md` 外，先阅读数据工程入口：

1. `quwoquan_data/README.md`

## 数据工程硬约束

- 一律遵守 `CLI prepare -> Agent semantic -> CLI validate + gate` 三段式。
- **执行推进主体是宿主 agent 会话**（[`DEC-027`](../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-027)）：阶段序、产物契约与交接协议由 `.agents/skills/content-production/` 拥有；每阶段经 `task stage-open` → `task stage-gate` → `task stage-close` 落 create-once authority-bound stage receipt，receipt 链 + 磁盘产物是跨会话交接与恢复的唯一状态源。仓库执行代码只允许两类——确定性 IO（下载、CAS、publish/release/ship 原子命令）与检查器（verify + schema）；禁止新增驱动/等待 agent、自动推进状态机或内置业务重试的编排代码，唯一豁免是 `quwoquan_data/scripts/content/execution/runner/loop_driver.sh`（≤50 行）与 `quwoquan_data/scripts/content/execution/runner/fleet_dispatcher.sh`（≤100 行，均无业务判断）。
- 新能力优先进入 `python3 quwoquan_data/scripts/cli.py <command>`，不要新增可直接运行的业务入口脚本。
- schema、blueprint、metadata、tag taxonomy、内容契约先行，再写下载/生产/发布逻辑。
- 内容生成以真实性、可追溯性和阶段结果为核心；不要用拍脑袋补全替代证据链。
- 新脚本归位到现有领域目录，禁止在仓库根创建平铺 `scripts/`。
- `content/execution/` 根只保留稳定工作包内核、CLI 薄绑定与 `handler.py`。其中
  `agent/`、`queue/`、`controller` 自动推进与 checkpoint 循环、`recovery/` rewind、
  campaign fleet 调度、managed SDK/provider 与 ReliableTask 为**退役中存量**（[`OPEN-006`](../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#open-006)）：
  不得作为新内容任务的执行入口，也不得再扩展；删除以 skill 驱动稳产证据为准入。
  搬迁必须原子更新 import 与测试，禁止旧路径 shim。
- 当前阶段未上线：旧模板拼文、区域硬编码、版本化 publish 路径、孤立脚本、不可追溯素材、弱事实证据一律直接清理，不做兼容。
- `.qwq_output/` 只允许可删除重建的运行产物、部署快照、证据与缓存；禁止把 `control_plane/prompts/templates/schema/specs/policies/reference` 等可复用真相源放入 output。Python venv 只是由仓内 `requirements.txt` 临时重建的 disposable cache，不是可复用测试环境、工程配置或发布资产；任何任务都不得要求该缓存预先存在。
- Python bytecode、pytest cache 只能写入 `.qwq_output/env/repo/local/**` 或测试隔离临时根；解释器工具缓存只能写入仓外的用户缓存目录（默认 `~/.cache/quwoquan/python-envs`），两者都不得进入 `quwoquan_data/**`。所有 Make/gate/pytest 入口必须以解释器 `-B` 启动、显式重定向 pytest cache，并在执行后运行 Data layout gate。
- 当前不保存或门控模型 token、价格、成本、预算或消费账本；Agent 运行证据只保留 provider、model、runId、promptSha256、结果与产物摘要。任何此类已退休字段或模块由 `verify reusable-data-contract` 阻断回潮。

## 内容供给端到端闭环
- alpha/beta/gamma/prod 的内容、Creator、实体、标签与发布媒体只能由同一环境中已激活的 immutable release 产生；Data Engineering 不拥有用户账号、评论、圈子、会话或消息。Alpha/Beta/Gamma 的这些领域事实只能由真实非生产主体经所属领域公开 command/event 创建，Prod 只接受真实用户或正式运营行为。禁止 T3/UAT、环境 bootstrap 或数据库脚本绕过公开契约创建内容对象，禁止把 contract fixture、测试 seed 或基础设施灰度探针投影到 feed/homepage/profile。

- 数据工程必须同时覆盖两条供给线：内容稿件线（article/image/moment/video/route 等 post package）与实体/标签/素材治理线（entity homepage、tagRefs、semantic mentions、review ledger、asset safety）。
- 标准链路为 `0.plan -> sources -> 1.download -> 2.quality -> 3.compose -> 4.draft -> 5.review -> publish -> release -> ship -> service importer`。
- 一个执行只有一个 `.qwq_output/data/tasks/<executionId>/` 工作包；失败以新 sequence + `retryOf` 重试，禁止静态 task、batch 双寻址或原地篡改输入。
- 正文只能由 Agent 基于 `writing_pack.json` 和 `prompt.md` 创作并写回，`generator=agent` 是交付面硬门；脚本不得拼正文。
- 图片、事实、来源权利、实体主页、tagRefs、semantic mentions、人审账本和发布态必须可追溯；不可追溯即不可发布。
- 内容载体按底稿形态路由：图片集合为主且文字只是标题/配文的是 `image` 图片作品；图文混合编排且源图随正文共同构成底稿的是 `article`；entity homepage 正文只允许 `encyclopedia-primary` 三百科闭集（Wikipedia、百度百科公开词条、今日头条百科）。官网、政府/文旅门户、OTA、Wikivoyage、360、Wikidata、OSM 与百科搜索不得投影为主页底稿或主证据。
- 信源政策按用途分轨，正文底稿与结构化事实不共用来源闭集：
  - **正文底稿**（source plan、source unit、writing pack、`primaryEvidenceRef`、`keyFacts`）仍锁在上面的三百科闭集，此项不放宽。
  - **结构化事实**（`openingHours`、`ticketPriceRange`、`recommendedDurationMinutes`、`bestSeasonTagRefs`、`altitudeMeters`、`officialWebsite`）额外允许官网与政府/文旅门户作为独立证据源。这些字段是可逐条核验的单值事实，官方站点是其第一手发布方，而百科词条在这类字段上最不及时；把它们绑死在百科只会让主页长期缺字段或写入过期值。
  - 每条结构化事实必须逐字段落 `factSources`（`sourceId`、`sourceClass`、抓取 URL、观测时间、置信度），缺任一项该字段不发布。官方来源与百科冲突时以官方为准并保留冲突记录，不得静默取其一。
  - 放开范围严格限于 `lanePolicies.homepage.structuredFactsPolicy.fields` 列出的字段；不得借官方来源把官方文案改写进正文、简介或 `keyFacts`。OTA、门户、媒体在两条轨上都仍然禁止。
- canonical `publish/` 只含通过 review 的自治 creators/entities/posts/media objects，及其引用的 `tags/<tagRef>/_definition.json` consumer snapshot；control-plane taxonomy 与 creator profile 仍是唯一可编辑静态输入，禁止复制整棵 taxonomy 或未引用标签进入 publish；事务写入前后使用内容摘要校验，不维护永久 freeze、迁移索引或兼容状态；
  release 唯一在 `.qwq_output/data/releases/{releaseId}`，环境证据唯一在
  `.qwq_output/env/{env}/runs/data-release/{releaseId}/{runId}`。`ship`/importer
  只读 canonical + desired state，禁止 retired path fallback 或 v1/v2 dual-read。
- immutable release lookup 只能由该 release 的 desired state、对象快照和显式引用的
  taxonomy snapshot 确定性派生；`homepageId`、环境 URL、import/readback 状态不得写入
  release payload，必须写入 environment append-only receipt。
- 数据产物最终必须能被 App 发现、搜索、消费和互动，并通过行为反馈进入推荐、运营指标和下一轮内容优化。

## 质量与 Review

- Review 必须先判定证据是否充足，再判定 prompt/template 是否失配，最后才判定创作执行问题；不同归因回退到不同阶段。
- 禁止百科罗列、机械收尾、模板化小标题、来源痕迹、不可商用素材、平台水印、未经改写长句复现。
- 内容角度、实体类型、tagRefs、manifest、asset id、source paths、发布账本必须一致；不一致先修契约或数据，不用代码绕过。
- 数据工程同样要补 `local_contract` schema/静态/CLI/模块、`api_integration` importer/真实存储或环境采样、`user_acceptance` 用户消费链路证据。

## 数据工程准出

Review 角色与证据闭包只读 `.agents/skills/review/references/registry.yaml`；缺 required evidence 时先补 spec/test/gate 或 repair stage，不把离线文件生成当成完成。

## 数据领域 E2E

- 数据任务不能停在离线文件层；必须说明如何进入 service importer、App 发现/搜索/消费、行为反馈和推荐/运营分析。
- 若涉及环境导入或发布，必须同步加载 `quwoquan_ops/AGENTS.md` 并收集 stackctl 证据。

## 推荐验证

- 优先使用 `python3 quwoquan_data/scripts/cli.py ...` 执行对应流程
- 新内容任务不运行仓内 `task preflight` semantic provider/key/model/SDK/capacity 检查，也不调用 `task execute`（含 plan-only）或 pool-dispatch/campaign。工作包唯一初始化命令是中性 `task init --carrier-demand <path> --candidate-bindings <path>`；输入必须是 confirmed demand 与 immutable bindings，命令只原子写三文件，失败不得手写补齐。每 stage 只跑契约点名的 deterministic input/layout/source/rights/runtime PRE。
- Data verify 只分三类，禁止再建第二套静态组合入口：
  1. **static all**：`python3 quwoquan_data/scripts/cli.py verify all` 是唯一静态 gate 组合。
  2. **on-demand**：需要具体 release/execution/环境参数的命令，如 `verify release-lifecycle`、`verify execution-readiness`、`verify publish-purity`。
  3. **runtime library**：`scripts/verify/*.py` 与领域模块可被 CLI/gate import；`__main__` 只供调试，不算正式入口。
- 若触及 CLI 入口契约，再跑 `python3 quwoquan_data/scripts/cli.py verify cli-first`
- 发布准出：`python3 quwoquan_data/scripts/cli.py verify release-lifecycle --release <releaseId>`
- 发布、采样、导入或环境数据变化后，补跑对应 `ship`、服务侧 importer 测试和与环境职责匹配的 `stackctl verify --env <env> --kind all --profile integration|release`。
- `scripts/` 顶层只允许 `cli.py`、`core/`、`content/`、`governance/`、`verify/`；稳定脚本名禁止任何阶段编号、批次编号或数字分片名。
- `quwoquan_data/**` 同时禁止 `.ruff_cache`、`.mypy_cache`、`.tox`、`.nox`、
  `.ipynb_checkpoints`、编辑器备份和临时脚本；所有 Python 文件必须由 scripts、
  三层测试、test support 或 generated 边界唯一归类。
