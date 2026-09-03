# L2 Business Capability：开发流程治理 (`development-workflow-governance`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让 Agent 使用目录原生规格、动态上下文和可执行门禁主导从概念到结果沉淀的全链交付，同时让人类以明确业务角色保有价值、范围、体验、风险、外部动作、商用与 outcome 的决定权。

## 2. 范围与非目标

### In Scope

- AppRoot/L1/L2/L3 的目录、规格、设计与验收规则。
- 宿主从 `.agents/skills/*/SKILL.md` metadata 发现的 Workflow Skill，其唯一 body、上下文链与工作流间交接契约。
- Agent 主导的概念、产品、体验、方案、交付授权、实施、质量/UAT、集成 CI、制品、Alpha/Beta/Gamma、商用、Prod、渠道、outcome 与沉淀全链阶段，以及人类角色在每阶段的输入、升级、验收和准出责任。
- 人类选择、授权、异常处置与事后检查的可理解交互；人类决定与技术 Review 分轨，Review 结果只作为证据。
- 按 `(workflow, deliverable, profiles)` 派发角色评审的 review 机制与分级语义。
- Cursor / Codex 两个 harness 的指令载体分配、渐进加载与上下文预算。
- 动态特性上下文、总览、变更影响报告和机器门禁。
- 本地优先持续集成和全链治理 observe-only 准入的单轨编排与证据分层。

### Out of Scope

- 业务领域自身的产品决定和 wire schema。
- 将当前会话计划、执行日志或派生报告提交为长期真相源。

## 3. Journey / Scenario 贡献

- 本能力是横切工程能力，不直接承接用户 Journey；它为所有 Journey 提供一致的实施和审核约束。

## 4. Story


- [`directory-native-sdd`](./directory-native-sdd/spec.md)：工具必须直接扫描目录与 Markdown；删除 `.qwq_output` 后仍可从受版本控制真相源重建上下文。
- [`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)：规则按全局、子树、工作流、Feature、角色与 adapter 分层；开发与 Review 共用精确 owner manifest，POST 评审固定在主审加最多一名专审，Cursor/Codex 从同一真相源加载。
- [`human-agent-delivery-interaction`](./human-agent-delivery-interaction/spec.md)：Agent 在冻结授权内主导完整交付，人类按业务 authority 角色提供独立输入、裁决硬门和价值取舍、授权外部动作并接受商用与 outcome 结果。
- [`objective-execution`](./objective-execution/spec.md)：Objective 与 Increment 通过 append-only TransitionEvent、deterministic reducer、authenticated authority readback 和 effect readback 可恢复推进；S4 准入直接消费 branch policy。
- [`hotl-expansion-control`](./hotl-expansion-control/spec.md)：S6 只读评估固定 cohort 人工瓶颈、checkpoint delta、紧急控制 proof 与 capability admission；当前 fail-closed 为 manual/单写者且不授予 mutation。
- [`local-continuous-integration`](./local-continuous-integration/spec.md)：按编辑、空闲、提交范围与推送范围调度 canonical checks，并以精确输入回执区分 `fast_green`、`scope_ready` 与 `release_ready`。
- [`governance-pipeline-observe-only`](./governance-pipeline-observe-only/spec.md)：只读聚合全链独立证据并给出 observe-only 准入解释，任何终态都不授予生产、商用或 HOTL mutation。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 目录原生单轨治理

- 目录结构必须直接表达 `AppRoot / L1 / L2 / L3`，不得维护人工索引或状态镜像。
- 规格、设计、metadata、代码与测试必须各自承担唯一职责，不得生成第二真相源。
- 长期未完成事项必须进入最低 owner 节点 `OPEN`；已解决事项转为当前要求或直接删除。

<a id="req-002"></a>
### REQ-002 命令与自然语言一致执行

- 自然语言与显式入口必须由宿主基于 `.agents/skills/*/SKILL.md` metadata 选择并加载同一 Skill body，进入同一 `PRE / DURING / POST / HANDOFF` 生命周期；不得由机器 boolean、route receipt 或中央 resolver 自证同轨。
- Skill PRE 先确定 exact target，再生成内容寻址、不可变的 compact owner manifest exact ref，并据此明确验收、证据层、OPEN 与风险；PRE 不自动派 Reviewer，开发期 POST 默认零 Reviewer 只报告命名 evidence，Review 只在用户显式 `/review` 或准出（lane→`dev1.0` PR、handoff、release）时派发；DURING 不再要求把角色 checklist 复制进回复。
- 普通单步闭环的 HANDOFF 只需产物、验证与未决项。只有跨会话未完成、多人并行、环境/发布、外部阻断、证据需要后继复用或用户显式要求交接时，才落 `.qwq_output/env/repo/runs/handoff/<轮次>/manifest.md`。
- 持久交接中的未决项必须落到「最低可关闭节点 `OPEN-###`」「Out of Scope」「下一工作流承接」之一；下游消费时证据字节或来源漂移即复跑，不得转抄结论。
- 教训沉淀由 `distill` 工作流（`.agents/skills/distill/SKILL.md`）承接：输入为交接单跨轮重复缺口、评审 finding 复发、用户同类纠正第二次，输出为带触发场景、根因层、建议落点、gate/check 绑定四字段的规则候选（无绑定候选不得标 MUST）。回写只走「提议 + 人确认 + prd/dev 正常工作流」，agent 不得绕过工作流直接修改规则资产。
- 资产垃圾回收报告（僵尸 reference、harness 分叉、AGENTS.md 与特性树重复正文）由 `make asset-gc-report` 可重复生成于 `.qwq_output/env/repo/runs/asset-gc/`，回收裁决走 distill / plan-next。
- 各工作流在自身 Skill 内就地声明 1～3 条完成证据；完成只认指定命令/测试/人工终态的真实结果，不认计数、todo 或抽样代理指标。
- 动态上下文、总览、变更报告和其他运行期可删除产物只写入 `.qwq_output`。由受版本控制中性源单向生成、且必须随仓库分发的 Cursor/Codex adapter 属于 tracked projection，不在此列，禁止手改。
- 目录、链接、章节、验收证据和禁止文件必须由可执行门禁校验。

<a id="req-003"></a>
### REQ-003 角色化评审与跨 harness 载体

- context manifest、Review plan 与 typed terminal 的字段和恢复语义只由 `quwoquan_ops/policies/agent_governance_contract.yaml` 拥有；workflow/profile/evidence 的可变路由只由 Review registry 拥有。
- profile 只拥有 specialist/evidence 路由，不拥有 Feature 事实，也不进入 owner manifest；Feature 上下文由 Skill PRE 生成的 immutable manifest exact ref 直接指向 spec/design/contracts 锚点，Review POST 原样复用该 ref，并仅按 `changed_paths + deliverable` 派生 profile。
- role 只定义职责与盲区；checklist 只放分级判定并引用 registry 的命名 evidence。功能、架构、页面和算法事实不得放在角色 reference 中。
- 指令真相源只存在于 `AGENTS.md`、`.agents/skills/` 与 Feature Tree；`.agents/skills` 是 Workflow 唯一 authoring source 与发现面，Cursor/Codex 专属目录只允许一行命令入口与生成的 Reviewer projection。
- 常驻 AGENTS、默认 owner manifest 与单 Reviewer 上下文必须遵守 canonical contract、registry 和门禁绑定的预算，任一超限都阻断。

<a id="req-004"></a>
### REQ-004 并行会话合法合入协议

- 合法合入态唯一定义为「scope-green + foreign-red 登记」：本会话 scope（当前计划与本会话 changed_paths）内影响面门禁全绿，且域外已知红以带归因与泛化判定的条目登记进该轮次交接单缺口段后，允许提交并推送 `dev1.0`。
- 不得以工作树整体全绿为合入前提——并行脏树是常态；也不得以域外红为由使用 `--no-verify` 绕过门禁。
- 混合文件（本会话与并行会话改动同文件）采用部分暂存提交，只提交本会话语义行。
- 归因或取证用的 stash/restore 操作必须以 pathspec 显式限定在本会话 scope 内文件，禁止无差别 `git stash`/`git checkout --` 触碰并行会话未提交增量——无差别恢复会把他会话未提交的 spec 增量静默还原回 HEAD 态。
- ContractGraph 静止窗口：contract view 构建与 accept 期间持有静止窗口，其他会话不得并发修改 canonical contracts；builder 对构建期漂移 fail-closed。遇 Graph 红先判定是否为窗口冲突（等待后复跑），再做失败归因。

<a id="req-005"></a>
### REQ-005 知识资产七类职责与动态 facets

- 知识资产只有七类 owner：Feature Tree（行为与验收，层级验收所有权按 [`specs/feature-tree/README.md`](../../README.md) 的结构契约执行）、AppRoot/L1/L2 design（DEC）、服务 contracts（wire）、最近 `AGENTS.md`（耐久执行不变量）、Workflow Skill（流程）、policies/hooks/gates/tests/Review registry（强制与评价，分层细则由 [L3 REQ-001](./agent-skill-review-context-organization/spec.md#req-001) 拥有）、外部 live authority 与 runtime receipt（证据）。同一事实只有一个可写 owner。
- 分类维度（authority、enforcement、scope、load-trigger、lifecycle）从路径、owner manifest、schema、binding 与 Git/provider 元数据动态派生；不建立手工维护的中央分类 registry、顶层 knowledge-base、tracked knowledge-extraction 根目录或中央 decisions/gotcha 库。
- 知识生命周期为 raw evidence → candidate → 人工确认 → canonical → enforced/evaluated → observed → superseded/removed。未经人工确认的 candidate 不得驱动不可逆实现、生产写入或 contract migration；superseded 必须声明替代锚点并清零 dangling references。
- 冲突裁决先识别事实类型再回该类型唯一 owner；两个 current canonical owner 声称同一事实时返回 typed `GATE_BLOCK(owner_conflict)`，不得以全局优先级掩盖双真相源。
- 强制度由 binding closure 决定：绑定可执行 gate/test/required check 的条款是 hard-gate，其余为 review-required 或 advisory；自然语言条款本身不冒充硬门。


<a id="req-006"></a>
### REQ-006 Agent 主导且人类 authority 可理解的全链交付

- Agent 必须主动研究、形成中性方案、实施、验证、取证和恢复；只有价值、范围、体验、风险、外部或不可逆动作、商用节奏与 outcome 接受需要具名 Human Authority 决定，常规实现细节不得反向甩给非技术角色。
- 每个需要人类决定的单元必须明确事前输入、独立影响评估、不可豁免硬门、唯一综合裁决、授权执行、证据责任和结果接受；缺席、超时、越权或职责分离不成立时 fail-closed。
- Human Authority 与 ReviewRole 必须分轨：Reviewer 只评价交付件和证据，任何 Reviewer PASS、投票或总分不得生成、替代或推导人类决定和执行授权。
- 人类界面必须以角色可理解的事实、对称选项、影响、未知项和后果支持补证据、转交与暂停；内部路径、工具、指纹与状态机术语不得成为业务角色必须理解的选项。
- 商用准备、生产 campaign、渠道公开和 outcome 接受必须分层裁定；上游通过不得冒充下游决定，硬门不得由 Limited Go、风险接受或多数意见绕过。

<a id="req-007"></a>
### REQ-007 本地反馈与治理准入保持单轨

- Local CI 只规划和调度 canonical checks，readiness queue、exact-input cache 与 receipt 都是可删除投影，不得形成第二事实台账；本地 `scope_ready`/`release_ready` 只证明所绑定的源码与测试范围。
- 治理流水线 admission 从 owner manifest immutable exact ref 开始，只消费各 owner 的 exact readback 并执行 observe-only 评估，不消费 workflow route evidence，也不得从 Review、本地 readiness 或调用方自报推导 Human、Commercial、Prod、channel、outcome 或 HOTL authority；任一终态的 Prod/HOTL mutation 均为 `false`。

<a id="req-008"></a>
### REQ-008 多车道并行交付准入

- 日常开发的物理隔离单元是六条长期 lane 分支各自的专属 worktree；`dev1.0` worktree 只承担集成、验收与过渡期收敛。分支角色与 PR 边由 [`daily-merge-release-strategy` REQ-001/REQ-002](../deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#req-001) 拥有，写并发由 [`objective-execution` REQ-003](./objective-execution/spec.md#req-003) 拥有，worktree 授权与身份由 [`local-worktree-lifecycle-governance` REQ-001](../system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#req-001) 拥有，端云闭环证据由 [`three-layer-evidence` REQ-005](../runtime-test-pyramid/three-layer-evidence/spec.md#req-005) 拥有；本 REQ 只声明工作流准入语义，不复制其值。
- 一个 Increment 只有一个 lead lane、一个 writer 与一个原子 PR；跨 owner 变更按 owner manifest 选定唯一 lead lane，不拆成多个并行 writer；`small-fix`/`refactor` lane 不降低影响面验证义务。简单只读问答不创建 Increment、lane 或 writer lease。
- Skill 显式入口与自然语言入口按 `REQ-002` 同轨进入同一生命周期后，PRE 必须校验当前 worktree 与 lead lane 一致；不一致时在任何 mutation 前 fail-closed，恢复动作限定为切换到正确 worktree、整体转移 lead lane、收窄 Increment 三种，禁止跨 worktree 隐式写入。
- 六条固定长期 lane 已由用户裁决立即开放，最多允许六个不同 lane writer 并发；启用后观察用于补齐真实证据，不作为渐进扩容或阻断当前准入的前置门。共享 host 资源（环境 cell、真机/模拟器、ContractGraph accept/codegen、可晋级 package、Docker prune）仍维持单 writer 租约与唯一 host coordination root；lane worktree 不得直接写共享 Alpha/Beta/Gamma，环境操作一律经 environment-ops 工作流进入。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 的仓库执行约束。
- 下游能力：仓库内所有业务节点、metadata、代码和测试。
- 读取事实：目录、Markdown、metadata、测试 `spec_ref` 与 Git diff。
- 写入事实：正式规格、设计、metadata、代码、测试与 machine-readable contract 是 authoring source；运行期派生结果写入 `.qwq_output`，Cursor/Codex tracked projection 只允许由其 contract 指定的中性源和生成器更新。
- 一致性要求：README 模板、命令和 gate 必须同步更新。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 目标节点可生成最小完整上下文

- GIVEN 仓库中存在被稳定 L1 根与 L2 DEC 适用工程根覆盖的目标 spec 或代码路径。
- WHEN 开发者生成默认 feature context 并执行特性树门禁。
- THEN 输出符合 canonical agent governance contract 的紧凑 manifest，指向唯一 owner 与直接 canonical 锚点，不拼接父链正文。
- AND 任何人工索引、节点级 acceptance、changelog 或中央 backlog 回潮都会阻断。

<a id="sit-002"></a>
### SIT-002 轮次交接与完成判据机器可裁定

- GIVEN 一个普通单步闭环或满足持久交接触发条件的工作流轮次。
- WHEN 工作流完成并由后继轮次消费证据。
- THEN 根据场景输出唯一适用的交付形式，普通闭环采用产物、验证和未决项，需持久场景采用可校验交接单并将未决项三向裁决至零悬空。
- AND 完成证据由对应 Skill 就地声明，证据指纹过期时下游复跑而非转抄结论。

<a id="sit-003"></a>
### SIT-003 教训沉淀与并行会话合法合入

- GIVEN 交接单出现跨轮重复缺口或评审同类 finding 复发，且存在多个并行会话共用工作树。
- WHEN 触发 distill 沉淀提议并有会话申请合入。
- THEN 规则候选带触发场景、根因层、建议落点与 gate/check 绑定，经人确认后走 prd/dev 正常工作流落地。
- AND 合入按「scope-green + foreign-red 登记」裁定：本会话 scope 内门禁全绿、域外已知红已登记进交接单缺口段。

<a id="sit-004"></a>
### SIT-004 知识资产唯一 owner 与分类回潮由结构门禁裁定

- GIVEN 一个新增或变更的知识资产按 `REQ-005` 声明了唯一 owner。
- WHEN 运行特性树门禁与 Agent 上下文治理门。
- THEN 违反唯一 owner、层级验收所有权或中央分类 registry 禁令的变更被 typed 判否。
- AND 历史知识资产迁移闭包只能由 tracked machine-readable fixture 从冻结 Git source object 重算；行数、source bytes、clause identity/digest、唯一 disposition、当前 target/anchor、terminal status 或 dangling reference 任一漂移均被结构门禁判否。

<a id="sit-005"></a>
### SIT-005 Local CI 与治理准入共用治理门禁链

- GIVEN Local CI 与治理 admission 的 canonical contracts、focused local contracts 和各自外部 OPEN。
- WHEN 执行两者公开 focused verify target、特性树门禁与仓库治理门禁链。
- THEN Local CI 只调度 canonical checks，admission 从 owner manifest immutable exact ref 开始返回保守 observe-only 评估并保持 Prod/HOTL mutation false。
- AND 本地 PASS 只证明当前 contract、实现与 fixture 自洽，不关闭外部身份、六角色 calibration、activation、环境、生产、渠道或 outcome 证据。

<a id="sit-006"></a>
### SIT-006 多车道 lead lane 与双入口准入

- GIVEN 六条 lane 分支与 `dev1.0` 各自的专属 worktree，以及一个已确定 lead lane 的 Increment。
- WHEN 会话经 Skill 显式入口或自然语言进入工作流并请求 mutation，或第二个会话在同一 lane worktree 上并行工作。
- THEN 当前 worktree 与 lead lane 一致时才允许 mutation；不一致时在任何 mutation 前 fail-closed，并给出切换 worktree、转移 lead lane、收窄 Increment 三种恢复动作；同一 lane 内的并行会话按根 `AGENTS.md` 共享工作树条款合作（检查活跃 writer、只编辑本任务字节），不由 hook 或 claim 文件互斥，冲突在 lane→`dev1.0` PR 准出时由 Delivery Gate 暴露。
- AND 两种入口在同一 lane 上进入同一生命周期并承担等价证据义务，不存在按入口差异化的旁路或降档。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 全树证据引用收口

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：部分节点仍以同节点 OPEN 声明尚缺直接测试 `spec_ref`，影响自动验收覆盖率。
- 完成判定：`SIT-001` 及全部节点验收锚点均有真实测试 `spec_ref`，且不再依赖 OPEN 代替证据。
- 依赖：各最低 owner Story 的测试与外部证据。

<a id="open-005"></a>
### OPEN-005 并行会话合法合入协议 gate/check 实现

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺可执行 gate/check 与直接测试 `spec_ref`——协议语义已冻结为 `REQ-004`（scope-green + foreign-red 登记、部分暂存、scope 内 pathspec、ContractGraph 静止窗口），但语义只靠自觉时，并行脏树互锁仍可能逼出 `--no-verify`（出处：调研转录 `0c4c608c-7219-47c2-bcda-5c66dcf93294`）。
- 完成判定：`SIT-003` 的合入子句（`.t2`）由真实 gate/check 覆盖——`REQ-004` 的合法合入态有可执行校验（如提交前 scope-green 自动判定、交接单 foreign-red 登记联动检查），ContractGraph 静止窗口约定有门禁化表达，且对应测试带 `spec_ref` 绑定。
- 依赖：commit gate、handoff manifest 与 ContractGraph 静止窗口门禁。

<a id="open-006"></a>
### OPEN-006 多车道准出 gate 与双入口证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：六条 lane 已立即开放；同 lane 并行会话不再由 hook/claim 互斥（该机制在实践中自锁、误导执行体绕道整仓 clone，已拆除），改为根 `AGENTS.md` 合作条款 + 准出时暴露冲突。lane PR ready 与 exact merge candidate 两级准出 gate 仍未实现，Skill 显式入口与自然语言入口在同一 canonical Skill 生命周期上的真实等价证据也未产生。启用后观察不阻断六车道。
- 完成判定：lane PR ready / exact merge candidate gate 闭合并覆盖 `SIT-006.t1`、`SIT-006.t2` 的 lead lane 一致性子句，且 `SIT-006.t3` 由至少一次 Skill 显式入口和一次自然语言入口在不同 lane 上完成等价 PRE、PR、evidence 与 retained-worktree resync readback 后删除。
- 依赖：[`daily-merge-release-strategy` OPEN-003](../deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#open-003)、[`objective-execution` OPEN-002](./objective-execution/spec.md#open-002)、[`three-layer-evidence` OPEN-002](../runtime-test-pyramid/three-layer-evidence/spec.md#open-002)。
