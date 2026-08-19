# quwoquan Codex Guide

本仓库使用“目录即树、节点自解释”的规格驱动开发。进入子目录时，先读取本文件，再读取路径上更近的 `AGENTS.md`。

## 唯一执行入口

非纯查询任务按以下顺序建立最小上下文：

1. 最近的 `AGENTS.md`。
   进入 `quwoquan_data/**` 时必须继续读取 `quwoquan_data/AGENTS.md`。
2. [`specs/feature-tree/README.md`](specs/feature-tree/README.md)。
3. AppRoot `spec.md/design.md`。
4. 目标 L1 `spec.md/design.md`。
5. 目标 L2 `spec.md` 与按需 `design.md`。
6. 目标 L3 `spec.md`。
7. 节点引用的 metadata 与测试。

已知目标路径时执行 `make feature-context TARGET=<spec-or-code-path>`；代码路径若被多个 L1 同优先级认领或没有 owner，返回 `GATE_BLOCK`，先修规格归属。

工作流语义由 `.agents/skills/<name>/SKILL.md` 定义：`explore`、`prd`、`design`、`dev`、`continue`、`plan-next`、`review`、`commit`，以及自动触发的 `environment-ops`、`content-production`、`incident-inspection`。技能由模型按 `description` 自动匹配，用户是否输入斜杠命令都不改变本契约。评审由 `.agents/skills/review` 在每个工作流的 PRE 与 POST 派发。

## 每次任务五段执行契约

两种入口只在第一步不同：用户直接描述意图时由 RESOLVE 推断，显式调用工作流技能时由调用方给定。两者产出同一结构化对象，之后走完全相同的五段——这是不让「意图驱动」与「显式调用」形成两套标准的关键。

### RESOLVE 定位

产出 `(workflow, deliverable, scope)` 三元组：

- `workflow`：上述十个工作流之一。定位不到唯一 workflow 时取**更早**的工作流，不要向后猜。
- `deliverable`：本次要交付的具体物（spec 节点、contract、页面、gate 等）。
- `scope`：In Scope / Out of Scope、`L1_domain_service / L2_business_capability / L3_story` 父链、AppRoot Journey/Scenario。

已知目标路径时执行 `make feature-context TARGET=<spec-or-code-path>`。

### PRE 准入

进入实现前必须明确，任一项存疑先回 `explore` 或 `prd` 刷新对应 `spec.md`，不要直接写实现：

- 目标与用户价值。
- 验收意图：`UAT / DOM / SIT / GWT / contract`。
- 测试证据层：`local_contract / api_integration / user_acceptance`。
- 当前 OPEN 与准出影响。
- 触发面判断：metadata-first、runtime error 链路、Mock 隔离、页面质量、Data CLI-first、stackctl、跨域 E2E、四环境、观测与回滚是否被触发。触达多个区域时证明 `Data -> Service -> App -> Behavior -> Recommendation -> Observability -> Environment` 无断点。

按 `.agents/skills/review` 的 registry 派发本工作流角色做前置评审。**任一 MUST 未满足即返回 `GATE_BLOCK`，停止并补齐，不进入实现。**

### DURING 执行中

把 PRE 评审选出的角色 checklist 复制进回复逐项勾选（checklist copy-in），MUST / MUST NOT 作为执行中约束持续生效，而不是等做完再检查。

### POST 自检

先按交付件的送审前自检清单自检，再调 `.agents/skills/review` 做后置评审：由它生成去重后的测试/gate 证据计划、执行并派发角色评审。失败回到 DURING；失败门禁不得包装为成功。

### HANDOFF 交接

固定交出以下四项。下一步的 RESOLVE **必须**消费上一步的 HANDOFF，断链即 `GATE_BLOCK`：

- **产出物**：文件、DEC 编号、受影响 metadata 路径，附 POST 评审结论。
- **未决项去向**：每一项必须落到「转最低可关闭节点的 `OPEN-###`」「判 Out of Scope」「下一工作流承接」三者之一，不允许悬空。
- **唯一合法下游**及其 PRE 所需输入；HANDOFF 必须覆盖下游输入段全部必需项。
- **证据链**：已跑的 gate 与结果，含失败项。

单步任务同样要交 HANDOFF，此时它就是对用户的交付说明：规格达成、三层测试、E2E、产品/UX、运营观测、自动化/门禁、OPEN 变化和剩余阻断。

## 特性树与文档规则

- AppRoot `spec.md` 拥有全应用目标、Journey、Scenario、UAT；AppRoot `design.md` 拥有全局架构与跨域约束。
- L1 `spec.md/design.md` 拥有领域事实、边界、工程归属、DOM 与领域设计。
- L2 `spec.md` 拥有能力组合行为和 SIT；仅达到设计门槛时保留 `design.md`。
- L3 只保留 `spec.md`，使用 REQ/GWT，设计决定上收到 L2/L1 DEC。
- 字段、path、operation、surface、route、event、metric、错误码和恢复语义只引用所属服务 `contracts/**`；跨服务 schema、共享协议和值定义引用 `quwoquan_service/contracts/metadata/**`，不在规格复制。
- 未完成能力、外部阻断、风险与未来规划写入最低可关闭节点的 `OPEN-###`。解决后删除 OPEN，并转为当前 REQ/设计事实；禁止中央 backlog 或完成日志。
- 不维护 feature registry/index、Journey registry、acceptance YAML、changelog、成熟度矩阵或第二套状态台账。
- 增量由当前会话目标、Git diff、代码/测试结果和 `make feature-tree-change-report` 表达；历史使用 `git log --follow`。
- 修改规格后运行 `make verify-feature-tree`；需要总览运行 `make feature-tree-overview`。

## 商用品质默认门

- Review：由 `.agents/skills/review` 按 `(workflow, deliverable, profiles)` 派发角色并行评审；profile 由 changed_paths 与 deliverable 派生，未匹配 profile 的角色与 gate 不加载，相同 gate 只执行一次。角色定义见 `.agents/skills/review/references/roles/`，**该目录是角色名的唯一真相源，其他文件不再自行列举**。重点盯契约漂移、无测试、无观测、体验断点、第二真相源和不合理抽象。
- 三层测试：`local_contract`、`api_integration`、`user_acceptance` 必须映射 UAT/DOM/SIT/GWT/contract；Remote 行为必须能回到测试树内对象级 typed double/Provider/Widget/领域规则覆盖，任何测试 double 不得进入环境 App。
- 四环境：`alpha`、`beta`、`gamma`、`prod` 的 App 使用同一 production Remote composition；环境只决定 runtime package、endpoint、容量与发布阶段，**不决定数据源**。任何环境禁止 fixture、直接数据库 seed 与派生投影预填。不存在 `prod-gray`，生产灰度只是 `prod` rollout stage。数据来源、测试数据分层构造与 capability 约束的细则由 [quwoquan_ops/AGENTS.md](quwoquan_ops/AGENTS.md) 拥有，此处不复制。
- 错误链路：metadata errors、HTTP 响应、端侧 mapper/UI、恢复动作、埋点、日志、告警和测试必须同源。
- 可观测与配置：新增页面、API、行为信号、推荐策略和数据发布必须声明 SLI/SLO、指标、采样、保留、告警、配置来源、灰度与回滚。
- 无法证明时返回 `GATE_BLOCK`，补规格、metadata、测试或运维证据。

## 编码总约束

- `quwoquan_service/services/<service>/contracts/**` 是该服务业务对象、wire 字段、错误码、path、route、surface、operation 与 decoder context 的唯一真相源；`quwoquan_service/contracts/metadata/**` 只保留跨服务 schema、共享协议和值定义。先 contracts，后 verify/codegen，再写业务逻辑，禁止手改 codegen 产物。
- 错误码使用 `MODULE.KIND.REASON`；动态上下文只进入 string-only `context.attributes`。
- Mongo/bson 可用 `_id`；客户端 HTTP/WS/DTO JSON 只认 canonical `id`/`postId` 等键。
- 契约单轨：禁止版本信封、wire 多键双读、dual-read/dual-write、长期 shim、compat/warn-only 逃逸和为错误实现加 fallback。
- 结果状态单义：任何返回值只能表达「在场有值」「在场为空」「缺席」「失败」之一。失败不得降级为 `null`/`nil`/空字符串/空集合，缺席不得塌陷为零值；字段可空性只由对象契约声明。四态模型、各语言禁令与 `catch` 内 `return null` 的两条合法出路见 `.agents/skills/review/references/roles/developer/references/result-state-semantics.md`。
- `.qwq_output/` 只存可删除、可重建的运行输出；删除后仍必须能凭受版本控制真相源重建。
- 源码树不得保留 `__pycache__/`、`*.pyc`、`*.pyo`、`.pytest_cache/`；缓存重定向到 `.qwq_output/env/repo/local/**`。
- 每个第一方服务以 `environments/<alpha|beta|gamma|prod>/` 作为环境自治入口，共享定义只存在于服务内 `config/schema.yaml`、`resources/` 与 `deploy/base/`；环境之间禁止继承。环境装配、部署、巡检、修复统一使用 `python3 quwoquan_ops/cli/stackctl.py`。
- 本地与远端只允许 `dev1.0`、`main` 两个分支：日常开发直接提交并推送到唯一集成真相源 `dev1.0`，唯一 PR 边为 `dev1.0 -> main` promotion；禁止临时分支和第三长期分支。`main -> dev1.0` 只允许 promotion 成功后的系统 fast-forward backsync，Prod source 必须是可达 `main` 的精确 SHA。
- 脏工作树是常态；禁止回滚、覆盖或清理与当前任务无关的用户改动。

## Python 脚本治理

- 稳定脚本角色只允许 `gate / cli / lib / generator / runner / tool / migration / hook`；角色与 owner 从物理树和引用关系实时派生，禁止提交脚本 registry、inventory、债务 baseline 或 orphan allowlist。
- 按树归位规则、命名禁令与 orphan 裁决见 `.agents/skills/review/references/roles/developer/references/python-scripts.md`；门禁 `make verify-python-script-governance`。

## 工作方式

- 默认中文说明与注释；代码标识符、命令和路径保持原文。
- 优先做可验证的小改动，执行与影响面匹配的 gate/test。
- 本地 `/commit` pre-commit 仅跑 L0 `quwoquan_ops/gate/commit_gate.sh`（目标 ≤10 分钟，硬顶 15 分钟）；全量 local_contract 由 CI Delivery Gate 分片承接，禁止把 `--no-verify` 当常规合入手段。
- 稳定、反复出现的规则写入最近的 `AGENTS.md`、特性树 README 或对应命令，不留在会话临时约定中。
