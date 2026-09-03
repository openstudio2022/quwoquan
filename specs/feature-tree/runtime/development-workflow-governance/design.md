# L2 Design：开发流程治理 (`development-workflow-governance`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收”需要 `directory-native-sdd` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`directory-native-sdd`](./directory-native-sdd/spec.md)：工具必须直接扫描目录与 Markdown；删除 `.qwq_output` 后仍可从受版本控制真相源重建上下文。
- [`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)：规则按唯一职责渐进加载，开发与 Review 共用 owner manifest，评审受固定角色预算约束，Cursor/Codex 同源加载。
- [`human-agent-delivery-interaction`](./human-agent-delivery-interaction/spec.md)：Human Authority 与 Review 分轨，Agent 在限界授权内主导 15 阶段交付，商用、生产 campaign、渠道和 outcome 使用不同决定与接受边界。
- [`objective-execution`](./objective-execution/spec.md)：Objective/Increment 的执行状态由 TransitionEvent 单轨拥有，executor 只消费 authenticated authority 与 effect readback，S4 准入从 branch policy 推导。
- [`hotl-expansion-control`](./hotl-expansion-control/spec.md)：S6 只拥有 HOTL applicability、固定 cohort 瓶颈、checkpoint delta、紧急控制 proof、capability admission 与 fallback，并动态消费 Human authority、Objective S4 与生产事实。
- [`local-continuous-integration`](./local-continuous-integration/spec.md)：基于 canonical EvidenceFingerprint 规划并调度本地 checks，逐级产出不可冒充外部证据的 readiness receipt。
- [`governance-pipeline-observe-only`](./governance-pipeline-observe-only/spec.md)：从 owner manifest 的 immutable exact ref 开始，只读汇聚 readiness、Review、Human、Objective、环境和发布 owner 的独立 readback，并维持零 authority/零 mutation 边界。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 的仓库执行约束。
- 下游能力：仓库内所有业务节点、metadata、代码和测试。
- 读取事实：目录、Markdown、metadata、测试 `spec_ref` 与 Git diff。
- 写入事实：正式规格、设计、metadata、代码、测试与 machine-readable contract 是 authoring source。运行期可删除产物写入 `.qwq_output`；Cursor/Codex adapter 是由中性 executor 单向生成的 tracked projection，禁止手改。
- 一致性要求：README 模板、命令和 gate 必须同步更新。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 目录结构和父子 spec 构成唯一特性树
- 决策：目录结构和父子 spec 构成唯一特性树。
- 理由：让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`directory-native-sdd`](./directory-native-sdd/spec.md)（目录原生上下文）
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 规则按稳定作用域分层，Workflow Skill 采用五段最小契约
- 决策：根 AGENTS 只放全仓不变量；最近子树 AGENTS 只放该子树每次变更都成立的不变量，不参与自然语言工作流路由。`.agents/skills/*/SKILL.md` 的 metadata 是唯一宿主发现面，body 是唯一 Workflow Skill 正文，并只保留触发与输入、执行、完成证据、失败停止、条件性交接五段。Feature 行为与设计只落 spec/design/contracts；角色只保留职责/盲区，checklist 只保留判定。
- 决策：删除共享 interaction/completion 跳转、强制 brief-back、checklist copy-in 与普通任务的持久交接。只有跨会话未完成、多人并行、环境/发布、外部阻断、证据需复用或用户显式要求交接时生成交接单。
- 决策：有显式 Cursor 入口的 Workflow Skill 与 `.cursor/commands` 双向一一对应；命令文件只是一行式入口，并指向同一 Skill body。`prd` 拥有可测试规格，`design` 仅在达到门槛时拥有 DEC，简单规格可直达 `dev`。
- 适用工程根：`.agents/README.md`、`.agents/skills`、`.cursor/commands`、`.cursor/hooks.json`、`.codex/hooks.json`
- 理由：常驻规则与递归 reference 会在任务开始前吃掉上下文；把功能事实放进角色或 harness 文件又会让开发与 Review 加载不同版本。稳定作用域分层让同一事实只有一个 owner，并让加载触发可判定。
- 被否决方案：继续以八段模板和共享完成表追求形式一致。也不保留功能角色 reference 再由 Cursor rule 指向，或提交 workflow manifest/规则 inventory 作为第二真相源。
- 关联要求：`REQ-001`
- 影响 Story：[`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)（规则与 Skill 分层）
- 关联验收：`GWT-001`

<a id="dec-003"></a>
### DEC-003 Review 使用主审加唯一专审、命名 Evidence 与定向复审
- 决策：Review plan、结构化 ReviewResult/Finding/Consolidation 与 typed terminal 由 canonical agent governance contract 单点拥有；workflow primary、profile specialist、预算与命名 evidence 路由由 registry 单点拥有。PRE/POST 只消费这两处真相源。实现可发射 `REVIEW.*` code 与 contract 静态闭集相等且 recovery 一对一。
- 决策：`explore` 与 `plan-next` 不产生送审交付件。`continue` 复用被恢复 workflow，`review` 不递归自审，`commit` 只做 lane 提交、不要求 Review evidence。这五个控制型 workflow 在 registry 中声明零 Reviewer；其他 workflow 在 registry 保留 primary/specialist 配置以供显式 `/review` 与准出派发，但开发期 POST 默认不派审——Review 触发点只在用户显式请求或准出（lane→`dev1.0` PR、handoff、release），硬门不进入日常开发。
- 决策：initial、finding-owner 定向复审、并发与总调用预算严格取 registry 的 limits；禁止自动第二轮复审、失败重试或 passed 角色陪跑。
- 决策：checklist 只引用 registry evidence ID 或客观 check。Board 按 contract 的 plan/fingerprint schema 装配、去重执行并共享证据，Reviewer 不拥有命令执行权。纯 consolidator 消费 current plan、fresh named evidence 与宿主外部提供的结构化 reviewer results，required/optional incomplete 分别收敛到 GATE_BLOCK/PR_WARN，按 finding ID 稳定去重并拒绝旧 fingerprint result；仓库实现不直接启动 Cursor Reviewer。
- 适用工程根：`.agents/skills/review`、`quwoquan_ops/cli/review_dispatch.py`、`quwoquan_ops/cli/review_consolidator.py`、`quwoquan_ops/cli/lib/review_terminal_contract.py`、`quwoquan_ops/tests/local_contract/gate/test_review_dispatch__cli__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_review_consolidator__local_contract_test.py`
- 理由：目标会话的 33 次 Reviewer 均成功却被多轮全量复审拖重，说明首要问题是无角色预算与无定向复审；近期模型/额度/连接错误又会被这种放大器成倍触发。
- 被否决方案：固定全角色 board、从 checklist 全文抽取 gate、Reviewer 缺证据时自行重跑、只以 HEAD SHA 复用脏工作树结论。
- 关联要求：L2 `REQ-003`、`REQ-004`；L3 `agent-skill-review-context-organization/REQ-006`
- 影响 Story：[`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)（评审预算与证据）
- 关联验收：`GWT-003`、`GWT-004`、`GWT-006`

<a id="dec-004"></a>
### DEC-004 Owner manifest 与 Cursor/Codex adapter 共享中性真相源
- 决策：Skill PRE 确定 exact target 后，`feature-context` 生成严格遵守 canonical agent governance contract 字段与预算的 compact manifest，并以内容摘要形成 immutable exact ref；expanded 格式仅供显式人工诊断。`explore`、`plan-next` 及 `continue` 的只读恢复以 best-effort 方式调用：唯一 owner 成功时保存并消费 ref，无 owner、多 owner或解析失败时记录 typed 结果，基于当前 Git 快照继续只读，不因此阻断整个控制流程，也不获得 mutation 授权。
- 决策：代码路径先按最长 L1 工程根确定领域，再读取该 L1 下 L2 DEC 的“适用工程根”与唯一“影响 Story”下钻。prd、design、dev 等 mutation workflow 进入写入前，以及用户显式或准出 Review 派发前，必须取得唯一且 current 的 immutable exact ref；ref 缺失、旧 schema、摘要漂移、owner 多义或锚点冲突时 fail-closed。显式/准出 Review 原样复用该 ref；manifest 不包含 profiles，Review profile 只由 current `changed_paths + deliverable` 派生且不复制 owner。控制型零 Reviewer workflow 不能包装送审交付件旁路 manifest。
- 决策：Reviewer executor 是受版本控制的中性 authoring source。生成器单向渲染必须随仓库分发的 Cursor Markdown 与 Codex TOML tracked projection，并检查缺失、漂移、孤儿和手改。运行期 plan/context 仍只写 `.qwq_output`。仓库删除 Claude Code 的入口、桥接和当前支持声明，历史 receipt 与模型族值保持可读。
- 适用工程根：`quwoquan_ops/policies/agent_governance_contract.yaml`、`quwoquan_ops/cli/lib/agent_governance_contract.py`、`quwoquan_ops/cli/lib/evidence_fingerprint.py`、`quwoquan_ops/cli/lib/evidence_generation.py`、`quwoquan_ops/cli/lib/review_fingerprint.py`、`quwoquan_ops/cli/evidence_runner.py`、`quwoquan_ops/cli/handoff_manifest.py`、`quwoquan_ops/cli/handoff_consumer.py`、`quwoquan_ops/gate/verify_handoff_manifest.py`、`.agents/skills/review/references/reviewer-executor.md`、`.cursor/agents`、`.codex/agents`、`quwoquan_ops/cli/feature_tree.py`、`quwoquan_ops/cli/lib/feature_tree`、`quwoquan_ops/tools/generate_agent_adapters.py`、`quwoquan_ops/tests/local_contract/gate/test_feature_tree__directory_native__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_feature_tree__clause_binding__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_agent_adapter_generator__tool__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_named_evidence_runner__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_handoff_manifest__gate__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_handoff_manifest_producer__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_evidence_fingerprint__contract__local_contract_test.py`
- 理由：默认 expanded context 曾拼入约 178KiB 父链正文，且 pageflip 两条路径落在不同 L1。Reviewer 真相源又反向放在 Claude Code adapter 目录下。精确 manifest 与中性 adapter 同时消除过载和 harness 倒置所有权。
- 被否决方案：把 Feature context 复制到 Review profile、保留 Claude Code adapter 作为 Cursor 兼容源，或让 Cursor/Codex 手工维护两份 Reviewer 正文。
- 关联要求：`REQ-002`、`REQ-005`
- 影响 Story：[`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)（owner manifest 与 adapter）
- 关联验收：`GWT-002`、`GWT-005`

<a id="dec-005"></a>
### DEC-005 上下文治理门以全 Story 约束为输入
- 决策：上下文预算门同时校验规则分层、owner manifest、Review Board、adapter 单轨和 Claude 活跃入口退休；它是约束执行器，不复制各 Requirement 正文。负例合同与 gate 使用同一实现字节，任何预算或注册表语义变化必须同步失败。
- 适用工程根：`quwoquan_ops/gate/verify_agent_context_budget.py`、`quwoquan_ops/tests/local_contract/gate/test_agent_context_budget__gate__local_contract_test.py`
- 理由：综合治理门必须看到完整 Story，而普通 Skill、Reviewer 或 adapter 只需要自己的最小 anchors。
- 被否决方案：让每个 harness 自行实现预算检查，或为了减少 manifest 条目而让综合 gate 只加载部分要求。
- 关联要求：L2 `REQ-001`、`REQ-002`、`REQ-003`、`REQ-004`、`REQ-005`；L3 `agent-skill-review-context-organization/REQ-006`
- 影响 Story：[`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)（综合治理门）
- 关联验收：`GWT-001`、`GWT-002`、`GWT-003`、`GWT-004`、`GWT-005`、`GWT-006`

<a id="dec-006"></a>
### DEC-006 知识七类唯一 owner、动态 facets 与 Skill-first 上下文顺序
- 决策：知识按 L2 `REQ-005` 七类划分，物理位置由唯一 owner 决定；facets 动态派生，不建中央自然语言 resolver、手工分类清单或知识第二正文。上下文装配唯一顺序为根 AGENTS → 宿主基于 `.agents/skills` metadata 选择 Skill → 唯一 `SKILL.md` body → Skill PRE 确定 exact target → 最近子树 AGENTS + compact manifest immutable exact ref → exact path#anchor contexts 与直接 tests/contracts。已知目标路径时可先读最近子树 AGENTS 以遵守路径不变量，但子树不参与自然语言路由；禁止 manifest-before-skill。Review profile 不属于 manifest，只在 POST 由 `changed_paths + deliverable` 派生。
- 理由：分类与位置解耦后，强制度由 binding closure 决定而非目录名；Skill-first 保证自然语言与显式入口由真实宿主加载同一 Skill body 和生命周期，而不依赖中央解析收据自证。
- 被否决方案：顶层 knowledge-base、中央 decisions/gotcha 库、session ledger、manifest-first 装配、八类知识对应八个物理目录。
- 约束与影响：GC 与 Review 按 facets 查询；违反唯一 owner 的新增内容 fail-closed。
- 关联要求：L2 `REQ-005`
- 影响 Story：[`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)（知识 facets 与上下文装配顺序）
- 关联验收：`GWT-001`、`GWT-002`

<a id="dec-007"></a>
### DEC-007 EvidenceFingerprint 单轨身份：digestPayload 与 receipt 分离
- 决策：目标态为 manifest、Review、handoff 与 evidence 复用共享同一 EvidenceFingerprint；digest 只覆盖版本化 digestPayload（git/workspace/assets/execution 语义输入），capturedAt/capturedBy 等 receipt metadata 位于摘要之外。canonical serialization、排序、缺席/空集合与 symlink 语义由 `quwoquan_ops/policies/agent_governance_contract.yaml#evidence_fingerprint` 定义。
- 理由：把采集时间混入身份会使同输入永不复用；各 schema 自定义影子 freshness 字段会产生第二身份算法。
- 被否决方案：每个消费者各自定义 baseSha/dirtyDigest；把 capturedAt 计入 digest。
- 约束与影响：任何 digestPayload 组成项漂移都拒绝复用旧 PASS、Reviewer 结论、manifest 或 handoff；同输入不同采集时间 digest 必须相同（contract fixture）。manifest、Review plan、命名 evidence 回执与 on-demand handoff producer/consumer 均只消费 canonical `evidence_fingerprint` receipt/ref/digest，不保留 legacy freshness 双读或第三种指纹算法。
- 决策：evidence runner 在首条 command 前以 plan changed paths、canonical contexts、registry command 与 review assets 重算 current fingerprint，每条 command 后和最终收口复核；tracked/untracked/deleted/renamed/symlink/context/registry command 任一变化在执行前零命令 blocker、执行中 stale/GATE_BLOCK，execution/result receipt 均保留真实 workspace digests。
- 决策：handoff producer 只消费真实文件形式的 canonical PASS named evidence receipt 与 current plan；consumer/verifier 从 payload、artifact 与 evidence receipt 重算 current freshness，同 HEAD 脏树漂移同样拒绝。证据行投影真实 command/exit/start-finish/source HEAD，下游只能取 canonical workflow registry。
- 关联要求：L2 `REQ-003`、L3 `REQ-004`
- 影响 Story：[`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)（evidence 单轨）
- 关联验收：`GWT-004`


<a id="dec-008"></a>
### DEC-008 Human Authority 与 Review 分轨并以 append-only DecisionUnit 派生授权
- 决策：`HumanAuthorityRole` 与 `ReviewRole` 使用物理分离的职责 namespace。ReviewResult/Finding 只作为技术证据，Reviewer PASS 不生成 HumanDecision、不满足 ResultAcceptor，也不派生任何副作用授权；两个 namespace 可以由同一 actor 分别承担，但不能互相代签。
- 决策：每个 `DecisionUnit` 在激活前闭合 RequiredInputProviders、IndependentImpactAssessors、HardVetoOwners、AccountableDecider、AuthorizedExecutor、EvidenceOwner、ResultAcceptor 七类责任。第一轮事实与第二轮对称方案独立封存，依次校验身份/范围/证据、硬门、合法选项、事实 owner 与价值裁决；多数票、未冻结总分和 Agent 推荐均不覆盖硬门。
- 决策：Human Decision 是 authenticated、append-only authority。执行授权只能从仍有效的决定派生，并受其目标、范围、动作、期限和停止条件约束。缺席、超时、越权、证据漂移、职责分离失败和决定消费竞争均 fail-closed。记录成功但状态消费失败时保留“已记录、未消费”，不得伪造迁移成功。
- 决策：同一 actor 的多角色提交仅满足 `role-record-only`；预冻结 policy 标明 `independent-principal-required` 时必须使用不同 authenticated actor。安全、合规、不可逆数据和生产关键授权是否要求独立 principal 由该 policy 决定，不因团队规模自动降级。
- 决策：`CommercialReadinessDecision` 不授权生产副作用；正常 Prod 只使用一次 `ProductionCampaignApproval` 绑定精确生产来源、不可变候选、流量阶段、SLO、窗口、停止条件和 rollback target，冻结范围内由自动技术 gate 推进。resume、候选或约束变化必须形成新决定。Production 授权动态消费 Objective-owned admission readback，Human Authority 不复制其机器事实。
- 决策：将来的独立 Human-Agent 交付机器 contract 由 [`human-agent-delivery-interaction`](./human-agent-delivery-interaction/spec.md) 唯一拥有 Human Authority、DecisionUnit、授权派生、商用与 production campaign 语义。它不得写入或从现有 `agent_governance_contract.yaml` 推断这些语义，也不得 dual-read。
- 适用工程根：`quwoquan_ops/policies/human_agent_delivery_contract.yaml`、`quwoquan_ops/cli/human_agent_delivery.py`、`quwoquan_ops/cli/lib/human_agent_delivery/`、`quwoquan_ops/gate/verify_human_agent_delivery_eval.py`、`quwoquan_ops/tests/local_contract/gate/test_human_agent_delivery__contract_router__governance__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_human_agent_delivery__commercial_evidence_projection__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_human_agent_delivery_calibration__gate__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_human_agent_delivery_eval__gate__local_contract_test.py`；与 `DEC-003` 至 `DEC-005` 的 Review/manifest owner 分离。
- 理由：技术 Review 能判断交付件是否满足规格，却无权替业务角色决定价值、范围、体验、风险、商用和 outcome；把 authority 与 Review 混为一体会让 PASS 隐式升级为不可逆授权，并放大推荐偏置与职责分离风险。
- 被否决方案：不扩充 Reviewer Board 让 8～11 个 Reviewer 投票，不由当前聊天用户一次同意覆盖所有角色，不让 Commercial Go 自动触发生产，不要求每个流量阶段重复人工点击，不以短命分支实现 S4，也不把 Human Authority 字段追加进现有 Agent Review contract。
- 约束与影响：人类交互只展示角色事实、对称选项、硬约束、未知项与后果；内部 contract 字段只进入审计投影。DecisionUnit、授权与外部 readback 未闭合前保持 L3 OPEN 阻断，不得以规格或 Review 完成宣称 runtime 可用。
- 关联要求：L2 `REQ-006`；L3 `human-agent-delivery-interaction/REQ-001` 至 `REQ-006`
- 影响 Story：[`human-agent-delivery-interaction`](./human-agent-delivery-interaction/spec.md)（角色化全链交付与 authority）
- 关联验收：`GWT-001`、`GWT-002`、`GWT-003`


<a id="dec-009"></a>
### DEC-009 Objective/Increment 状态执行采用 TransitionEvent 单轨与 authority/effect 两事件协议
- 决策：`Objective` 是端到端业务目标状态边界，`Increment` 是其内可独立授权、验证和集成的工作单位。两者只共享事件协议，不共享聚合 identity。它们的唯一执行状态 authority 是本地 append-only `TransitionEvent` journal 加版本化 deterministic reducer。journal 证明 execution state，不证明 Human identity。Human Authority 语义继续只由 `DEC-008` 与 `human-agent-delivery-interaction` Story 拥有。
- 决策：command/query 分流为 CAS append、显式 recover/materialize、authorized effect command、state readback 与 admission inspect。每次 append 同时比较 expected head 与 generation。journal 以 descriptor-relative、`O_DIRECTORY`/`O_NOFOLLOW` 的 inode-bound walk 建立受信边界：canonical root/kind/subject/events 固定 trusted effective UID + `0700`，authoritative/lock/staging/derived 固定 `0600` regular single-link；ancestor/component symlink（含 broken）、owner/mode/type/link drift 与 subject rename/recreate 全部 fail closed。每个首次 mkdir 显式 chmod 后先 fsync parent 再 fsync child。writer lease 返回仅内部 under-lease 路径可消费、绑定 canonical root+subject inode 且持有 root/kind/subject/events/lock descriptor/identity 的 capability，公开 append/recover 自行取 lease，不接受 boolean bypass。
- 决策：event 先写入 trusted events dir 内私有 staging，完成 canonical JSON write + file fsync 后，Darwin 通过 `renameatx_np(..., RENAME_EXCL)` 在同一 dirfd exclusive no-replace 发布最终 generation，再 fsync events directory；不支持该原语的平台 fail closed，禁止降级为 overwrite rename。未发布 staging 非 authority 且只可在 validated lease 下清理；已发布完整 event chain 是 crash recovery authority，snapshot/head 仅以 descriptor-relative safe replace+fsync 形成派生物。完整连续且 digest/identity/reducer version 可验证的 event chain 在 snapshot/head 缺席、落后或部分 materialize 时不判 tamper，只能由显式 recovery 或 append 前恢复在 exclusive writer lease 下确定性重建；只读 readback 零写并返回 recovery-required。event 缺口、摘要/hash chain、identity/reducer version 或受信节点漂移才 tampered。
- 决策：Objective 与 Increment 分别使用 contract 冻结的 versioned transition graph；每条边固定 `action / from_state / to_state`，terminal 只能经显式 reopen/restart 边离开。executor 在任何 effect invoke 前完成 transition admission，拒绝闭集内任意跳。
- 决策：executor 的顺序固定为 authority provider exact-byte readback + verifier 校验 → transition admission → 幂等追加 `human_decision_recorded` → 以持久化 effect identity 调用 effect → exact effect readback → 追加 `state_transition_committed`。decision event 冻结完整 command envelope digest 与非空 effect ID。pending 恢复必须精确匹配 subject/source/target/action/payload/authority/evidence/provider/receipt/effect identity，mismatch 使用专用 conflict 且零 effect、零 transition。readback 不接受空 effect ID 或仅按 key 查询；只有 identity exact `applied` 可迁移状态，`unknown`/identity drift 保持 pending readback 且禁止副作用重试。
- 决策：authority 是注入 port，验证 actor、role、scope、expiry、EvidenceFingerprint、decision kind 与 action。生产默认无 provider 即 typed blocker；Human `AuthorizationGrant` projection 保持 non-authenticated/non-executable 且零 mutation。`provider_kind=test` 只用于 local contract，明确不可成为 release evidence。
- 决策：effect adapter 也由注入 port 承担，并必须支持 idempotency 与 exact readback。executor 不把进程退出码当 applied，不在未知结果下重试；rollback 是新的受授权 effect/TransitionEvent，不改写历史。
- 决策：S4 admission 每次直接加载 canonical `branch_policy.yaml`，Objective execution 的 canonical contract `quwoquan_ops/policies/objective_execution_contract.yaml` 单点拥有 admission/readback 的 exact wire、status/reason/terminal、并发、temporary flag、digest 与 blocked 动态 detail 规则；独占 writer lease 与 CAS 使竞争只有一个 winner，loser 零 effect、零 event，只读 query 可并行。Human/HOTL contract 不复制 S4 机器事实。本 DEC 直接关联 L3 `specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md`。
- 适用工程根：`quwoquan_ops/policies/objective_execution_contract.yaml`、`quwoquan_ops/cli/objective_execution.py`、`quwoquan_ops/cli/lib/objective_execution/`、`quwoquan_ops/gate/verify_objective_execution.py`、`quwoquan_ops/tests/local_contract/gate/test_objective_execution__journal_authority__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_objective_execution__journal_security__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_objective_execution__executor_admission__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_objective_execution__gate__local_contract_test.py`
- 理由：状态事件、Human authority 和外部 effect 是三种不同事实；先记录决定、再确认 effect、最后迁移状态，能在 crash、超时和并发下恢复，又不让本地 JSON 冒充身份 authority。branch policy 动态推导消除 S4 双真相源。
- 被否决方案：不采用 mutable snapshot、Issue/PR/check 或 Agent 自报作为状态源，也不把 Human Decision 与状态迁移合并成一个事件；不把合法 event-first crash 当 tamper，不允许无 lease readback 顺手修复派生物，不允许 caller boolean 冒充 lease，不在 final generation 上原地写入，也不以 overwrite rename、字符串路径重开或不支持平台 fallback 降级安全语义。拒绝闭集内任意状态跳跃、空 effect ID 按 key readback、pending 命令部分字段匹配、命令退出 0 即迁移、unknown outcome 自动重试、本地投影授权执行、在 Human contract 固化分支列表/S4 数值或以短命分支制造并发 writer。
- 约束与影响：所有运行输出只进入 `.qwq_output/env/repo/local/objective-execution/process/**`；typed terminal 与恢复动作由 objective execution contract 单点拥有。真实 identity/provider、headless executor 与外部 effect readback 未闭合时，两个 L3 OPEN 保持阻断，local contract PASS 不升级为 release readiness。
- 关联要求：`objective-execution/REQ-001` 至 `REQ-003`。
- 影响 Story：[`objective-execution`](./objective-execution/spec.md)（状态、执行与准入；Human authority producer 仅为依赖，不是本 DEC 的改动 owner）
- 关联验收：`objective-execution/GWT-001`、`objective-execution/GWT-002`、`objective-execution/GWT-003`


<a id="dec-010"></a>
### DEC-010 HOTL expansion 采用只读 evaluator 与版本化外部 activation
- 决策：S6 的 `contract` 与 `inspect` 是 query 边界，evaluator 不写状态、不执行 effect、不提供 activate/grant/resume command。首版不存在 activation verifier/provider。调用方提交的 receipt 及 authenticated/exact/release 布尔值只作未受信审计输入，任何非空 receipt 都以 `ACTIVATION_PROVIDER_UNAVAILABLE` 返回 not_admitted/manual。未来 capability grant 必须由新的 contract/version/implementation 消费独立 authenticated activation authority 的 exact-byte readback。
- 决策：evaluator fail-closed 地核对 R0/R1 applicability、固定 cohort 与 9000bp coverage、durable human wait、checkpoint delta、不可移除决定、pause/deny/abort/revoke 的 exact ACK+独立 effect readback、commercial authority、resume/revoke/override 和 activation provider availability；R2-R4 硬阻断。authority decision kind 必须属于 canonical Human contract 闭集，首版 policy allowlist 仅接受 `delivery_authorization`，不把 `routine_execution` 当 authority。
- 决策：S4 每次动态调用 Objective execution `inspect_admission()` 并消费 canonical `quwoquan_ops/policies/objective_execution_contract.yaml` 拥有的 admission/readback descriptor。HOTL canonical contract `quwoquan_ops/policies/hotl_admission_contract.yaml` 只声明 source、动态消费/并发比较和禁止复制，不拥有 wire/reason/terminal。本 DEC 直接关联 L3 `specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md` 与所消费的 Objective L3 `specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md`。
- 决策：首次 S4 provider/descriptor/validation 失败在公开 inspect 边界直接返回 `OBJECTIVE_ADMISSION_BLOCKED` typed blocked，携带 owner-defined 或 Objective emergency blocked fallback 且 provider 不重试；规范校验后的 `status=blocked` readback 同样立即返回该 typed blocked，detail 取 readback reason，并原样保留该 S4。
- 决策：canonical serialization/digest/ref 依赖异常在 inspect 边界以 `EVALUATION_IDENTITY_FAILED` typed blocked 返回，并保留依赖名、首次 detail 与已验证的 S4 readback。S4 故障和 identity 故障都不得折叠为输入无效。
- 决策：S4 只作为 evidence 和 requested concurrency gate，所有 blocked/not_admitted 以及首版 eligibility 结果都由 canonical `current_fallback` 保持最大写并发 1、grant 不可执行和零 mutation。
- 决策：Objective canonical contract 无法加载时，HOTL 只能调用 Objective owner 模块内不依赖 YAML 的 emergency blocked S4 helper，且 HOTL 不维护 S4 字段或值的影子。
- 决策：HOTL canonical contract 自身无法加载时只返回独立最小 contract terminal，不得构造 inspection result 或 admission facts。stable id 在重复检查、计数、排序与 digest 前先归一为 NFC。
- 决策：disconnect、audit failure、ACK timeout、identity drift、authority decision kind 越界和 activation provider 缺失均 fail-closed；安全 fallback 固定为 manual、禁止 checkpoint reduction、grant 不可执行、零 mutation。Human override 优先，revoke 后零新动作，resume 必须获得新的 Human decision。
- 适用工程根：`quwoquan_ops/policies/hotl_admission_contract.yaml`、`quwoquan_ops/cli/hotl_admission.py`、`quwoquan_ops/cli/lib/hotl_admission/`、`quwoquan_ops/gate/verify_hotl_admission.py`、`quwoquan_ops/tests/local_contract/gate/test_hotl_admission__contract__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_hotl_admission__evaluator__local_contract_test.py`
- 理由：S6 只能优化已证明的人工等待，不得夺取 Human authority、Objective 状态/S4 或 production/channel/outcome owner；query/command 物理分离、首版不信任调用方 receipt 与未来 activation 版本边界能避免本地评估自我授予执行权。
- 被否决方案：不接受从 runner queue/job started 推导人工等待、ACK 等同 effect、静态复制 S4、local test provider 或调用方自报 receipt 作为 release evidence、满足本地 facts 即直接 grant，或通过长期 fallback/shim 暗中扩大写并发。
- 约束与影响：首版只返回 blocked、not_admitted 或 eligible_for_activation，且稳定保持 single-writer/non-executable/zero-mutation；所有外部 OPEN 关闭前，local contract PASS 不得被表述为 S6 admitted 或 release-ready。
- 关联要求：L3 `hotl-expansion-control/REQ-001` 至 `REQ-003`
- 影响 Story：[`hotl-expansion-control`](./hotl-expansion-control/spec.md)（S6 HOTL 扩展准入）
- 关联验收：`hotl-expansion-control/GWT-001`、`hotl-expansion-control/GWT-002`、`hotl-expansion-control/GWT-003`


<a id="dec-011"></a>
### DEC-011 Local CI 只调度 canonical checks 并输出可删除 readiness 投影
- 决策：Local CI 的 planner/runner 只根据 changed paths、owner manifest 与 canonical profile 调度仓库既有 checks；queue、cache、receipt 与 inspect 输出均是绑定 EvidenceFingerprint 的可删除投影，不登记 check 真相、完成状态或 release 状态。当前无宿主自动 edit readiness 接线，queue 在真实 producer/consumer SLO 闭合前按版本化 contract 仅作 advisory；Git hooks 保留 staged/branch boundary，不消费 readiness receipt，也不自行复制全面测试编排。
- 决策：公开 `verify-local-readiness` 使用受管 pytest runner 执行 focused local contracts，再只读 inspect 当前 readiness；`gate_repo.sh` 只调用该 canonical target 一次。
- 适用工程根：`quwoquan_ops/policies/local_readiness_contract.yaml`、`quwoquan_ops/cli/local_readiness.py`、`quwoquan_ops/ci/local_readiness_planner.py`、`quwoquan_ops/hooks/local_readiness_after_edit.py`、`quwoquan_ops/gate/commit_gate.sh`、`quwoquan_ops/tests/local_contract/ci/test_local_readiness__core__local_contract_test.py`
- L1 归属：Local CI 工程根由 runtime L1 `Agent` 根认领，本 DEC 将其唯一收窄到 `local-continuous-integration`；`quwoquan_ops` 项目级 App 根不拥有这些精确路径。
- 理由：调度器复制 check 清单或维护中央 readiness ledger 会制造第二 CI 事实源；精确输入投影让本地反馈可复用且不越权。
- 被否决方案：不建立常驻 CI daemon、中央 readiness ledger、独立 check registry，也不由 pre-commit 自动运行全面测试。
- 约束与影响：本地 `scope_ready`/`release_ready` 只证明绑定的源码与测试范围，不声称环境、设备、UAT 或发布就绪。
- 关联要求：`local-continuous-integration/REQ-001` 至 `REQ-003`
- 影响 Story：[`local-continuous-integration`](./local-continuous-integration/spec.md)（本地就绪调度与回执）
- 关联验收：`local-continuous-integration/GWT-001` 至 `local-continuous-integration/GWT-003`

<a id="dec-013"></a>
### DEC-013 治理 pipeline admission 只读聚合并保持零 authority/零 mutation
- 决策：governance pipeline admission 是 query-only 聚合边界，从 Skill PRE 产出的 owner manifest immutable exact ref 开始，只消费各 owner 的 exact readback，并按 schema、freshness、fingerprint 与证据层级返回保守终态；它不消费 workflow route boolean、resolution receipt 或其他路由证据。无独立 authenticated activation verifier 时最多 eligibility；所有终态保持 `production_ready=false`、`commercial_ready=false`、`hotl_admitted=false` 与 Prod/HOTL/global mutation false。
- 决策：公开 `verify-governance-pipeline-admission` 使用受管 pytest runner 执行 evaluator/CLI/gate focused local contracts，再执行 canonical verify script；`gate_repo.sh` 只执行 verify script 一次，companion tests 由既有 companion target 承接。Review consolidation 只提供唯一公开 focused verify/test target，不在仓库门禁链重复执行。
- 适用工程根：`quwoquan_ops/policies/governance_pipeline_admission_contract.yaml`、`quwoquan_ops/cli/lib/governance_pipeline_admission/`、`quwoquan_ops/cli/governance_pipeline_admission.py`、`quwoquan_ops/gate/verify_governance_pipeline_admission.py`、`quwoquan_ops/tests/local_contract/gate/test_governance_pipeline_admission__evaluator__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_governance_pipeline_admission__contract_cli_gate__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_governance_pipeline_admission__evidence_bundle__local_contract_test.py`
- L1 归属：Governance pipeline admission 文件由 runtime L1 `Agent` 根认领，本 DEC 将其唯一落到 `governance-pipeline-observe-only`；项目级 `quwoquan_ops` App 根不构成竞争 owner。
- 理由：聚合器自行签发 authority 会把源码、Review 或 readiness PASS 升级为外部事实；query-only 聚合保留各证据 owner 和外部决策边界。
- 被否决方案：不接受调用方自报 activation、Review PASS、本地 `release_ready`、released/published/outcome 相互推导或任何隐式 mutation。
- 约束与影响：外部 identity、六角色 calibration、hosted authority/activation、环境/设备/UAT、Commercial/Prod/channel/outcome 继续由 `governance-pipeline-observe-only/OPEN-001` 至 `OPEN-003` 与外部 owner 关闭；本地 PASS 只证明 current evaluator/contract/fixture。
- 关联要求：`governance-pipeline-observe-only/REQ-001` 至 `REQ-003`
- 影响 Story：[`governance-pipeline-observe-only`](./governance-pipeline-observe-only/spec.md)（observe-only 治理准入）
- 关联验收：`governance-pipeline-observe-only/GWT-001` 至 `governance-pipeline-observe-only/GWT-003`

## 5. 失败与恢复

- Board 只按 canonical agent governance contract 的 `terminal_codes` 映射等级、自动重试许可与唯一恢复动作；未知 terminal fail-closed。
- owner/profile/scope 或受管字节变化时重新生成 contract-compliant plan，不复制旧 evidence 或 passed 角色结论。
- 禁止回退到全角色 board、旧 checklist gate、HEAD-only 指纹、Claude 入口或手工 adapter 双写。

## 6. 质量与观测

- 门禁必须可重复、输出精确文件和原因，并在仓库规模下保持秒级目录扫描。
- Review 报告严格使用 contract 的 plan fields；观测只记录角色调用、evidence、上下文字节、profiles 与 typed 中断，不记录敏感内容。

<a id="hotl-runtime-matrix"></a>
### 场景化 HOTL 运行矩阵

<!-- HOTL_RUNTIME_MATRIX:START -->

本节是运行时场景的**单一投影**，不是 workflow resolver、执行状态台账或第二份流程正文。流程细节仍由对应 [Workflow Skill](../../../../.agents/README.md)、Human/HOTL/Review/Local CI owner contract 及分支发布规格拥有；矩阵只回答“在当前场景加载什么、谁能阻断、谁负责恢复”。运行 receipt 可删除，不回写本矩阵。

#### 运行矩阵读法与能力边界

- 宿主能力只用三态：`V=verified` 表示当前仓库机器检查或真实运行证据直接证明；`D=declared` 表示配置/规范已声明但缺真实宿主 smoke；`U=unsupported` 表示当前仓库没有该入口/接线。`V(repo)` 只证明仓库结构，不冒充宿主端到端行为。
- Cursor 三入口必须分开：`C-NL` 是模型依据 Skill description 的自然语言语义选择，**非确定性**且不是 resolver；`C-Skill` 是宿主直接点名/斜杠调用已发现 Skill；`C-Cmd` 是 `.cursor/commands/<name>.md` 自定义 prompt 命令，其“加载并执行 Skill”只是提示文本，不是 include/alias。当前仅 8 个 `C-Cmd` 有 `V(repo)` 薄壳，另外 4 个为 `U`。
- Codex 只按自身真实证据标记：共享 `.agents/skills` discovery 与 `.codex/hooks.json` 当前最多为 `D`，无 `.cursor/commands` 等价 stub 为 `U`；不得从 Cursor 的入口、hook payload 或结果外推 Codex 已支持。
- 目标加载顺序是项目不变量：根 `AGENTS.md` → 宿主选择唯一 Skill body → PRE exact target → 最近子树 `AGENTS.md` + compact owner ref → exact contracts/tests。自然语言是否选中及完整执行生命周期必须由真实宿主 smoke 证明，静态 metadata 不能自证。
- `read-only` 指不修改 tracked truth/source、不执行外部 mutation；允许把 context、query、queue、receipt、日志等可删除证据写入 `.qwq_output/**`（`runtime-evidence-write`），因此不等于文件系统零写入。
- Cursor/Codex 当前只接线 observe-only/fail-open 的 shell/worktree context 与会话提醒，不是安全边界；Cursor 没有 after-edit hook，Codex PostToolUse 也未接线。保留的 after-edit 脚本仅供显式验证或未来 producer 使用。Git `pre-commit`/`pre-push` 只守 staged/branch 边界，lane PR、handoff、promotion 与 release 的 required checks 才是准出 hard gate。
- Human 证据分三态：`H-D=declared_binding`（contract 声明交互点）、`H-P=projected_interaction`（projector 已向正确角色投影 exact subject）、`H-R=human_decision_received`（已收到绑定 exact subject 的可验证决定 ref）。Skill 引用 binding 或 Agent 发进度消息只证明 `H-D`，不能冒充 `H-P/H-R`。
- `evaluation_succeeded` 只表示 evaluator 成功完成判断，可同时得到 `not_admitted`；它不推出 `admission_granted`、`authority_created` 或 `mutation_allowed`。正式 authority/provider/readback 缺失时 fail-closed。
- 当前 HOTL owner 的安全回退固定为 `not_admitted / manual / max_write_concurrency=1 / grant_executable=false / mutation_allowed=false`。Objective/branch policy 已允许六条长期 lane 的人工协作 writer，是另一层政策；它不把 HOTL 自治提升到六并发。
- Review 当前执行模型是 **Agent convention + 人工签收**：仓库能生成/校验 plan、evidence、result 与 consolidation，但没有已验证的 PR/handoff/release 事件到角色执行器的自动桥。开发期默认零 Reviewer；仅显式 Review 或准出触发，范围为 workflow primary + 最多一名最高优先级 specialist；Reviewer PASS 与人工签收都不创建 Human/Prod authority。

#### Skill 场景

| 场景 | 输入/入口 | 宿主能力（D/V/U） | 加载规则/上下文 | PRE | DURING | POST | 阻断层 | Review 触发/范围 | Human / Agent 责任 | 恢复 | 预算/效能风险 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SKILL:commit | 用户明确要求 commit；C-NL/C-Skill/C-Cmd | C-NL[D]、C-Skill[D]、C-Cmd[V(repo)]；Codex discovery[D]/Cmd[U] | 根规则 + [commit Skill](../../../../.agents/skills/commit/SKILL.md)；既有 owner/evidence 可引用但不补造 | 确认授权、branch/HEAD、精确 scope、secret/owner/writer | 显式 pathspec 暂存，检查 staged diff，运行 L0 后创建 commit | 回读 SHA、文件、message、剩余 status | Agent 在 mutation 前 fail-closed；Git pre-commit staged boundary 是 hard boundary | 本 Skill 零 Reviewer；后续 lane PR 才触发 | binding 为 H-D；用户明确意图允许本地提交，但不是正式 H-R authority；Agent 只提交本 scope | 修复 staged blocker、重新精确暂存或重新取得明确授权 | L0 必须有界；禁止全仓 Review/readiness、清理他会话或 `--no-verify` |
| SKILL:content-production | 内容执行/恢复/immutable release；主要 C-NL/C-Skill | C-NL[D]、C-Skill[D]、C-Cmd[U]；Codex discovery[D]/Cmd[U] | 根规则 + [content-production Skill](../../../../.agents/skills/content-production/SKILL.md)；按阶段只载一个 stage contract | 送审 release 需唯一 exact target/owner ref；纯查询可无 manifest | 依次消费 canonical owner facts/receipt，阶段 create-once；源码 mutation 转 Feature workflow | 闭合 execution→release→import/readback→App UAT；纯诊断标 `no-review-deliverable` | rights/source/identity/UAT/authority 缺失在对应阶段阻断；查询本身可只读结束 | 产生 content-release 即 release 准出；primary + 最多一专审 | H-D；环境/发布/外部写需 H-P/H-R；Agent 不补造 source、rights、UAT | 从首个失败阶段 exact receipt 恢复，identity 漂移则重建本阶段 | 阶段引用闭包、模型能力、外部 I/O 与 UAT 成本高；不得预载全链正文 |
| SKILL:continue | “继续/续跑”及现有 todo、diff、handoff | C-NL[D]、C-Skill[D]、C-Cmd[V(repo)]；Codex discovery[D]/Cmd[U] | 根规则 + [continue Skill](../../../../.agents/skills/continue/SKILL.md) + 被恢复 Skill 的原上下文 | 重建 HEAD/status、todo、fresh evidence、durable handoff，识别原 workflow | 完整继承原 workflow；不自建 resolver/manifest/Review | 报告恢复分支、产物、证据、剩余 todo/typed blocker | 只读恢复可 best-effort；原 workflow mutation/准出规则照常阻断 | 继承原 workflow；continue 自身零 Reviewer | H-D；Agent 不凭聊天记忆扩大授权；需决定时由原 workflow 获得 H-P/H-R | stale receipt 按原 owner 重跑；不唯一先 explore | 最大风险是加载错误旧上下文；只载恢复所需 exact refs，禁止复制历史摘要 |
| SKILL:design | 冻结 spec 上的架构/恢复/观测决策 | C-NL[D]、C-Skill[D]、C-Cmd[V(repo)]；Codex discovery[D]/Cmd[U] | 根规则 + [design Skill](../../../../.agents/skills/design/SKILL.md) + owner ref + REQ/contracts/现有 DEC | 唯一 target/owner/ref，spec 已冻结且达到设计门槛 | 仅在 L2/L1 design 写 DEC；明确边界、失败、回滚、test seam | 运行 feature-tree 验证，报告 evidence，默认未评审 | owner/spec/contract/回滚不可判定时写前阻断；普通编辑无宿主 hard gate | 显式 `/review` 或 lane PR/handoff 准出；primary + 最多一专审 | H-D；方案取舍需要对应角色 H-P/H-R；Agent 负责中性方案与实现约束 | 回 prd/explore 补规格/owner/恢复条件 | compact manifest ≤8KiB；expanded 仅诊断，避免重复父链与全角色上下文 |
| SKILL:dev | 已冻结 Story/修复的代码实现 | C-NL[D]、C-Skill[D]、C-Cmd[V(repo)]；Codex discovery[D]/Cmd[U] | 根规则 + [dev Skill](../../../../.agents/skills/dev/SKILL.md) + 最近子树规则 + exact contexts/tests | 唯一 target/owner/ref、scope、验收、OPEN、共享写点 | authoring-source-first，Red/Green/Refactor，运行影响面最小证据 | 报告字节、命令/退出码、未验证项；默认零 Reviewer | owner/ref/required evidence 在 mutation/完成边界 fail-closed；无宿主 edit hook | 显式 Review 或 lane PR/handoff/release；primary + 最多一专审 | H-D；常规实现由 Agent 主导，范围/风险/外部动作漂移需 H-P/H-R | 回 prd/design/explore 或修复首个 typed blocker | 防止全仓测试、重复 gate 与 reviewer context 放大；按 impact 最小闭环 |
| SKILL:distill | 第二次同类纠正、复发 finding/gap | C-NL[D]、C-Skill[D]、C-Cmd[U]；Codex discovery[D]/Cmd[U] | 根规则 + [distill Skill](../../../../.agents/skills/distill/SKILL.md) + 原生 handoff/review evidence | 确认至少两个可引用实例、根因层与候选 owner | 形成触发/MUST/落点/gate 绑定候选，不直接改规则 | 输出候选、证据与人工裁决状态 | 单样本/无判据只 advisory；未获人确认不得进入规则 mutation | 仅用户要求准出；候选本身不自动派审 | H-D；规则落地必须先有 H-P/H-R 确认；Agent 只提案和去重 | 收集第二样本或交 prd/design/dev 正常落地 | 防止把日志/聊天扩成中央知识台账；只保留最小证据 refs |
| SKILL:environment-ops | health/inspect/package/deploy/gray/rollback | C-NL[D]、C-Skill[D]、C-Cmd[U]；Codex discovery[D]/Cmd[U] | 根规则 + [environment-ops Skill](../../../../.agents/skills/environment-ops/SKILL.md)；按 operator 角色渐进加载 | release-evidence 需唯一环境 target/owner ref；只读 status 可无 manifest | 仅经 stackctl；query 与 mutation 分流，读 canonical topology/readback | 分层报告 package/health/runtime/UAT/release/rollback receipt | 只读查询允许 `.qwq_output` 证据写；deploy/repair/Prod 缺 authority 硬阻断 | 产生 release-evidence、handoff 或 release 准出；primary + 最多一专审 | H-D；外部/不可逆/Prod 必须 H-P/H-R 与正式 authority；Agent 先安全 readback | 运行 doctor/inspect，白名单 repair；超白名单请求新授权 | 环境锁、设备、网络、构建与长日志高成本；严格超时并用 ref 传日志 |
| SKILL:explore | 非平凡变更的只读归属/风险调查 | C-NL[D]、C-Skill[D]、C-Cmd[V(repo)]；Codex discovery[D]/Cmd[U] | 根规则 + [explore Skill](../../../../.agents/skills/explore/SKILL.md)；owner context best-effort | 收窄 exact target，读取当前 diff/writer；不猜 owner | 只读定位 In/Out、验收层、依赖、后继 Skill；可写 `.qwq_output` context | 返回 target/ref 或 typed owner 结果、风险、建议下游 | 无/多 owner 不阻断只读；任何 tracked/external mutation 禁止 | 零 Reviewer | H-D；Agent 调查，价值/范围歧义才请求 H-P/H-R | 继续只读收窄；仍不唯一则停止，不进入 mutation | 搜索范围和 expanded context 易膨胀；默认 compact、按路径渐进加载 |
| SKILL:incident-inspection | ES/异常/trace/fingerprint/日报 | C-NL[D]、C-Skill[D]、C-Cmd[U]；Codex discovery[D]/Cmd[U] | 根规则 + [incident-inspection Skill](../../../../.agents/skills/incident-inspection/SKILL.md)；按 inspector 角色加载 | 送审报告需 fingerprints 唯一 owner/target/ref；临时查询可无 manifest | 只读 query/脱敏/聚类/复现判断；可写 `.qwq_output` 报告证据 | report-only 或 inspection-report；源码修复转 Feature workflow | credential/sample 缺失 typed block；无确定复现不判代码 bug；不改线上状态 | 显式 Review 或 report 进入 handoff；primary + 最多一专审 | H-D；Agent 先止损建议与调查，真实事故动作/恢复接受需 H-P/H-R | 缩小时间窗、补脱敏样本、转 environment-ops/dev | 遥测体量、PII、网络查询风险；有界窗口、脱敏、只传 refs |
| SKILL:plan-next | 轮次收口与后续最小计划 | C-NL[D]、C-Skill[D]、C-Cmd[V(repo)]；Codex discovery[D]/Cmd[U] | 根规则 + [plan-next Skill](../../../../.agents/skills/plan-next/SKILL.md) + plan/diff/evidence；owner best-effort | 确定轮次 target，核对真实文件/证据而非 todo 标记 | gap 仅裁决 fix-now/最低 OPEN/Out of Scope | 输出真实完成项、每个 gap 去向、后续可测目标 | owner 不明不阻断只读；required blocker 不得包装完成 | 零 Reviewer | H-D；优先级/范围/预算选择需 H-P/H-R；Agent 负责证据核对 | stale 证据重跑；目标不明回 explore | 防止把计划或完成日志变 tracked 台账；只引用 current diff/receipts |
| SKILL:prd | 用户价值/范围/验收的 spec mutation | C-NL[D]、C-Skill[D]、C-Cmd[V(repo)]；Codex discovery[D]/Cmd[U] | 根规则 + [prd Skill](../../../../.agents/skills/prd/SKILL.md) + compact owner ref + canonical contracts | 唯一价值、scope、target/owner/ref 与可测结果 | 在最低节点更新 REQ/GWT/OPEN，不实现代码、不复制 wire | 运行 feature-tree 验证，报告 ref/evidence，默认未评审 | 价值/scope/owner/contract 不唯一时写前阻断 | 显式 Review 或 lane PR/handoff 准出；primary + 最多一专审 | H-D；产品范围/验收冻结必须 H-P/H-R；Agent 负责中性规格与可测性 | 回 explore 补事实/owner，或补 contract/验收 | 防止规格正文、矩阵与测试排列组合重复；默认 context ≤8KiB |
| SKILL:review | 用户显式评审或准出 Review | C-NL[D]、C-Skill[D]、C-Cmd[V(repo)]；Codex discovery[D]/Cmd[U] | 根规则 + [review Skill](../../../../.agents/skills/review/SKILL.md) + exact owner ref + registry/checklists/evidence refs | 主会话确定 target/owner/scope/验收/evidence；PRE 零 Reviewer | evidence 去重执行，再按约定调用 primary + 最多一 specialist；Reviewer 不补跑 gate | consolidation、findings、角色完成状态与人工签收；PASS 仍非 authority | 仅显式/准出边界 hard；stale/incomplete/required failure fail-closed，不影响普通开发 | 本行即触发；范围仅 current changed paths + deliverable，修复只定向复审 | H-D；当前角色执行是 Agent convention，人工签收负责接受；Human Authority 仍需独立 H-P/H-R | 修复首个 finding/evidence，scope 变更新建 Review，禁止自动重试链 | registry 上限 2 并行/最多 4 次；24KiB 是控制面预算，最终 assembled input 仍有超限风险 |

#### 执行边界场景

| 场景 | 输入/入口 | 宿主能力（D/V/U） | 加载规则/上下文 | PRE | DURING | POST | 阻断层 | Review 触发/范围 | Human / Agent 责任 | 恢复 | 预算/效能风险 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BOUNDARY:session | Cursor/Codex startup/resume | Cursor session hook 当前接线[U]、every-shell reminder[D]；Codex SessionStart[D] | 仅根规则与会话提醒；不预载所有 Skill | 识别 repo/branch、未合入 worktree 与 active writer | 提醒/观测应 fail-open；不得自动取得 mutation authority | 可写 `.qwq_output` reminder sentinel/last-error | 执行面 hook 不得 exit 2；session 无 hard gate | 无；仅在用户随后显式/准出时 | H-D 不因 session 自动升级；Agent 选择后继 Skill | 显式运行 lifecycle/diagnostic，宿主不支持则标 U | every-shell fallback 有高频进程成本；应迁到受支持 session 事件且保留显式诊断 |
| BOUNDARY:shell | shell 命令请求 | Cursor beforeShell hooks[D]；Codex PreToolUse[D]，均无真实宿主 smoke | 当前 Skill + command；hook 只看最小命令形状 | 识别 CLI-first/worktree 创建提示与用户授权 | 始终 allow/附上下文；命令自身权限与 Skill 规则独立 | 记录必要提示，不生成 PASS/admission | observe-only hook 非安全边界；命令内显式 gate 可 hard block | 无自动 Review | 人决定授权边界；Agent 不把 hook allow 当授权 | 改用 canonical CLI/命令，策略不可读时显式诊断 | 每条 shell 启进程、YAML/git 探测会放大延迟；未命中应最早短路 |
| BOUNDARY:edit | Write/Edit/ApplyPatch 后事件 | Cursor after-edit[U]；Codex PostToolUse[U/not_wired]，真实 smoke[OPEN] | 当前 Skill/target；宿主不自动 enqueue，脚本仅显式/未来 producer | 写前由 Skill 校验 owner/ref/授权，POST 不能补 PRE | 编辑已发生；Agent 按需显式运行 readiness/enqueue | receipt/inspect 返回 advisory，不生成隐式 scope_ready | required checks/Review admission 在显式 readiness/准出阻断；queue backlog 不阻断 scope/release | 开发期零；显式/准出才 Review | Agent 保持 scope；Human 只处理范围/风险漂移 | 显式运行 `local_readiness.py enqueue|worker --once|inspect` 或 readiness | 无自动 consumer；exact-pending/foreign-pending 均 advisory，待真实宿主与消费 SLO 验证后再升级 |
| BOUNDARY:commit | Git commit 边界（通常经 commit Skill） | Git hook[V(repo)]；Cursor/Codex 只负责发起命令 | commit Skill + staged path identity；不加载完整 Review | 精确 staging、secret/PII/generated/cache/branch 检查 | pre-commit staged boundary；成功后原子 commit | post-commit 仅轻量 mark-due/fail-open；回读 SHA | pre-commit 是本地 hard boundary，但不消费 Review/readiness/本矩阵 gate | 零；lane PR 再审 | 明确用户提交意图；Agent 不混入他会话字节 | 修复 staged boundary 后重试，不 clean/reset | 秒级目标；不得运行全仓 context gate、全量 inventory 或普通 commit Review |
| BOUNDARY:push | lane 同名 push / 禁止直推集成发布分支 | Git pre-push[V(repo)]；宿主能力不参与判定 | branch policy + exact push updates | 回读 local/remote ref 与 actor/update | 只允许 policy 声明更新；不消费 local readiness receipt | 报告 push/readback；不产生 release eligibility | pre-push branch policy hard block；网络失败保持未知 | 普通 lane push 零；创建 lane PR 后触发 | 用户授权外部 push；Agent 不把 push 当 integration/release | 修复 ref/remote/branch，必要时转合法 PR 边 | 只做 branch policy；禁止全仓测试、旧 refs 污染与重复 readiness |
| BOUNDARY:lane-pr | `lane/* → dev1.0` exact candidate | Hosted PR/CI[D]；lane PR ready/exact merge candidate gate 尚有 OPEN | owner/candidate refs、impact checks、branch policy、Review artifacts | 验 head/base、candidate SHA、owner/scope、required checks 可达 | CI 重跑 required checks；不得信任本地 PASS 或开发机 worktree 状态 | 合入 readback；retained lane 随后 fast-forward resync | 这是集成 hard gate；当前未实现部分保持 OPEN，不宣称已自动准出 | 必触发 current candidate Review；primary + 最多一专审 + 人工签收 | 工程/质量接受；正式 hosted authority 缺失时对应声明 fail-closed | 修复 candidate/evidence，更新同一 lane PR；合入后 resync | 避免每 shard 重跑 common governance；Hosted 不探测本机六 worktree |
| BOUNDARY:handoff | 跨会话/人/host、环境发布、外部阻断或证据复用 | producer/consumer[V(repo)]；自动宿主触发桥[U] | current owner/candidate、named evidence、Review consolidation、OPEN | 仅 canonical 触发时创建；普通闭环使用 `no_persistent_handoff` | create-once manifest，exact refs/fingerprint，不转抄结论 | consumer 重验 freshness 并回读接手结果 | triggered handoff 是 hard boundary；stale/missing refs fail-closed | 触发准出 Review；范围为 handoff exact candidate | Agent 生产/验签；人工签收接手；正式决定仍需 H-P/H-R | 重跑 stale evidence、重建 current handoff，不能改写旧 manifest | 防止每轮都持久化、重复 evidence 和大日志；仅存 refs/摘要 |
| BOUNDARY:dev1.0-main | `dev1.0 → main` promotion PR | branch/source gate[V(repo)]；Hosted protection/live authority[D] | promotion SHA、required checks、Review/release evidence、main reachability | 确认唯一合法 promotion 边与 exact candidate | Hosted checks/人工签收；不执行正式 Prod apply | merge 后 main 为发布来源，system backsync 需 CAS readback | promotion 是 release-source hard gate；main direct push 永远拒绝 | 必触发 release 范围 Review；不复用 lane PR 的 stale结论 | release/engineering/quality 分责；PR approval 不等于 Prod H-R | 修复 checks/evidence 或新 candidate；禁止 force/自动 merge | promotion 全量但应去重 common checks；Hosted API 不可读即 fail-closed |
| BOUNDARY:release | main-reachable candidate 的 package/环境/Prod campaign | stackctl/CI 部分[V(repo)]；正式 identity/authority/provider[U/D] | release Skill/owner contract、immutable candidate、环境/Commercial/Prod readbacks | 先做只读 capability/authority preflight；缺正式 authority 立即停 | package→非生产验证→guarded activation；每层独立 readback | released/published/outcome 分层，post-release observation 不反推准入 | release/Prod 是最高 hard gate；authority/provider/readback 缺失 fail-closed | 必触发 release Review + 人工签收；Review PASS 不授 authority | H-D→H-P→H-R 必须按层闭合；Agent 只在 exact grant 内执行并止损 | 补正式 issuer/approval/credential/readback；漂移后重新决定 | 构建/设备/环境成本最高；先 fast-fail，分层超时，日志 content-addressed |

#### 机器约束与引用

- 本节由 `make verify-agent-context-budget` 的 `HOTL 运行矩阵` 检查验证：单一 marker 区段存在、12 个 `SKILL:*` 和 9 个 `BOUNDARY:*` 场景齐全、列头完整且区段不超过 32KiB。该检查属于按需/准出上下文治理，不得进入普通 commit 的 staged static selection。
- Workflow 唯一正文与入口分工：[`.agents/README.md`](../../../../.agents/README.md)；Skill/Review 上下文 owner：[`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)。
- Human 三态与正式决定边界：[`human-agent-delivery-interaction`](./human-agent-delivery-interaction/spec.md)；HOTL 当前 fallback：[`hotl-expansion-control`](./hotl-expansion-control/spec.md)；observe-only 聚合：[`governance-pipeline-observe-only`](./governance-pipeline-observe-only/spec.md)。
- Git hook/readiness 边界：[`local-continuous-integration`](./local-continuous-integration/spec.md)；六 lane 与 promotion/release 来源：[`daily-merge-release-strategy`](../deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md)。

<!-- HOTL_RUNTIME_MATRIX:END -->
