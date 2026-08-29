# L2 Design：开发流程治理 (`development-workflow-governance`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收”需要 `directory-native-sdd` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`directory-native-sdd`](./directory-native-sdd/spec.md)：工具必须直接扫描目录与 Markdown；删除 `.qwq_output` 后仍可从受版本控制真相源重建上下文。
- [`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)：规则按唯一职责渐进加载，开发与 Review 共用 owner manifest，评审受固定角色预算约束，Cursor/Codex 同源加载。

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
- 决策：根 AGENTS 只放全仓不变量，最近子树 AGENTS 只放该子树每次变更都成立的不变量。Workflow Skill 只保留触发与输入、执行、完成证据、失败停止、条件性交接五段。Feature 行为与设计只落 spec/design/contracts；角色只保留职责/盲区，checklist 只保留判定。
- 决策：删除共享 interaction/completion 跳转、强制 brief-back、checklist copy-in 与普通任务的持久交接。只有跨会话未完成、多人并行、环境/发布、外部阻断、证据需复用或用户显式要求交接时生成交接单。
- 决策：有 Cursor 命令的 Workflow Skill 与 `.cursor/commands` 双向一一对应；命令文件只作一行式发现入口。`prd` 拥有可测试规格，`design` 仅在达到门槛时拥有 DEC，简单规格可直达 `dev`。
- 适用工程根：`.agents/README.md`、`.agents/skills`、`.cursor/commands`、`.cursor/skills`、`.cursor/hooks.json`、`.codex/skills`、`.codex/hooks.json`
- 理由：常驻规则与递归 reference 会在任务开始前吃掉上下文；把功能事实放进角色或 harness 文件又会让开发与 Review 加载不同版本。稳定作用域分层让同一事实只有一个 owner，并让加载触发可判定。
- 被否决方案：继续以八段模板和共享完成表追求形式一致。也不保留功能角色 reference 再由 Cursor rule 指向，或提交 workflow manifest/规则 inventory 作为第二真相源。
- 关联要求：`REQ-001`
- 影响 Story：[`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)（规则与 Skill 分层）
- 关联验收：`GWT-001`

<a id="dec-003"></a>
### DEC-003 Review 使用主审加唯一专审、命名 Evidence 与定向复审
- 决策：Review plan 的字段与 typed terminal 由 canonical agent governance contract 单点拥有；workflow primary、profile specialist、预算与命名 evidence 路由由 registry 单点拥有。PRE/POST 只消费这两处真相源。
- 决策：`explore` 与 `plan-next` 不产生送审交付件。`continue` 复用被恢复 workflow，`review` 不递归自审，`commit` 只消费已评审增量。这五个控制型 workflow 默认不自动派审，其他 workflow 禁止关闭 automatic review。
- 决策：initial、finding-owner 定向复审、并发与总调用预算严格取 registry 的 limits；禁止自动第二轮复审、失败重试或 passed 角色陪跑。
- 决策：checklist 只引用 registry evidence ID 或客观 check。Board 按 contract 的 plan/fingerprint schema 装配、去重执行并共享证据，Reviewer 不拥有命令执行权。
- 适用工程根：`.agents/skills/review`、`quwoquan_ops/cli/review_dispatch.py`、`quwoquan_ops/tests/local_contract/gate/test_review_dispatch__cli__local_contract_test.py`
- 理由：目标会话的 33 次 Reviewer 均成功却被多轮全量复审拖重，说明首要问题是无角色预算与无定向复审；近期模型/额度/连接错误又会被这种放大器成倍触发。
- 被否决方案：固定全角色 board、从 checklist 全文抽取 gate、Reviewer 缺证据时自行重跑、只以 HEAD SHA 复用脏工作树结论。
- 关联要求：`REQ-003`、`REQ-004`、`REQ-006`
- 影响 Story：[`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)（评审预算与证据）
- 关联验收：`GWT-003`、`GWT-004`、`GWT-006`

<a id="dec-004"></a>
### DEC-004 Owner manifest 与 Cursor/Codex adapter 共享中性真相源
- 决策：`feature-context` 的默认 manifest 严格遵守 canonical agent governance contract 的字段与预算；expanded 格式仅供显式人工诊断。
- 决策：代码路径先按最长 L1 工程根确定领域，再读取该 L1 下 L2 DEC 的“适用工程根”与唯一“影响 Story”下钻。开发 PRE 与 Review POST 使用同一 resolver；重复或缺失声明 fail-closed，profile 不复制 owner。
- 决策：Reviewer executor 是受版本控制的中性 authoring source。生成器单向渲染必须随仓库分发的 Cursor Markdown 与 Codex TOML tracked projection，并检查缺失、漂移、孤儿和手改。运行期 plan/context 仍只写 `.qwq_output`。仓库删除 Claude Code 的入口、桥接和当前支持声明，历史 receipt 与模型族值保持可读。
- 适用工程根：`quwoquan_ops/policies/agent_governance_contract.yaml`、`quwoquan_ops/cli/lib/agent_governance_contract.py`、`.agents/skills/review/references/reviewer-executor.md`、`.cursor/agents`、`.codex/agents`、`quwoquan_ops/cli/feature_tree.py`、`quwoquan_ops/cli/lib/feature_tree`、`quwoquan_ops/tools/generate_agent_adapters.py`、`quwoquan_ops/tests/local_contract/gate/test_feature_tree__directory_native__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_feature_tree__clause_binding__local_contract_test.py`、`quwoquan_ops/tests/local_contract/gate/test_agent_adapter_generator__tool__local_contract_test.py`
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
- 关联要求：`REQ-001`、`REQ-002`、`REQ-003`、`REQ-004`、`REQ-005`、`REQ-006`
- 影响 Story：[`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)（综合治理门）
- 关联验收：`GWT-001`、`GWT-002`、`GWT-003`、`GWT-004`、`GWT-005`、`GWT-006`

<a id="dec-006"></a>
### DEC-006 知识七类唯一 owner、动态 facets 与 Skill-first 上下文顺序
- 决策：知识按 L2 `REQ-005` 七类划分，物理位置由唯一 owner 决定；facets 动态派生，不建中央 registry。上下文装配唯一顺序为 根+最近 AGENTS → Skill metadata RESOLVE → 唯一 SKILL.md body → Skill 请求 feature-context → exact path#anchor contexts → 直接 tests/contracts/profile refs。(workflow, profile) 的选择先于 feature-context 请求、由已选中的唯一 Skill 决定，禁止 manifest-before-skill。
- 理由：分类与位置解耦后，强制度由 binding closure 决定而非目录名；Skill-first 保证同一任务在自然语言与显式命令下装配同一上下文。
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
- 约束与影响：任何 digestPayload 组成项漂移都拒绝复用旧 PASS、Reviewer 结论、manifest 或 handoff；同输入不同采集时间 digest 必须相同（contract fixture）。迁移窗口内 Review 复用的唯一 consumed 身份仍为 `review_plan.fingerprint_inputs`，`evidence_fingerprint` 被消费者采用后即 supersede 该职责。收敛由 [L3 OPEN-002](./agent-skill-review-context-organization/spec.md#open-002) 追踪，窗口内不得出现第三种指纹算法。
- 关联要求：L2 `REQ-003`、L3 `REQ-004`
- 影响 Story：[`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)（evidence 单轨）
- 关联验收：`GWT-004`

## 5. 失败与恢复

- Board 只按 canonical agent governance contract 的 `terminal_codes` 映射等级、自动重试许可与唯一恢复动作；未知 terminal fail-closed。
- owner/profile/scope 或受管字节变化时重新生成 contract-compliant plan，不复制旧 evidence 或 passed 角色结论。
- 禁止回退到全角色 board、旧 checklist gate、HEAD-only 指纹、Claude 入口或手工 adapter 双写。

## 6. 质量与观测

- 门禁必须可重复、输出精确文件和原因，并在仓库规模下保持秒级目录扫描。
- Review 报告严格使用 contract 的 plan fields；观测只记录角色调用、evidence、上下文字节、profiles 与 typed 中断，不记录敏感内容。
