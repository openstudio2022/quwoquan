# L2 Business Capability：开发流程治理 (`development-workflow-governance`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收。

## 2. 范围与非目标

### In Scope

- AppRoot/L1/L2/L3 的目录、规格、设计与验收规则。
- 工作流技能（`explore/prd/design/dev/continue/plan-next/review/commit` 与自动触发的 `environment-ops/content-production/incident-inspection`）的统一模板、上下文链与工作流间交接契约。
- 按 `(workflow, deliverable, profiles)` 派发角色评审的 review 机制与分级语义。
- 跨 harness（Cursor / Codex / Claude Code）的指令载体分配与上下文预算。
- 动态特性上下文、总览、变更影响报告和机器门禁。

### Out of Scope

- 业务领域自身的产品决定和 wire schema。
- 将当前会话计划、执行日志或派生报告提交为长期真相源。

## 3. Journey / Scenario 贡献

- 本能力是横切工程能力，不直接承接用户 Journey；它为所有 Journey 提供一致的实施和审核约束。

## 4. Story



- [`directory-native-sdd`](./directory-native-sdd/spec.md)：工具必须直接扫描目录与 Markdown；删除 `.qwq_output` 后仍可从受版本控制真相源重建上下文。
- [`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)：顶层 Skill 只收录完整工作流并套用统一八段模板，评审按 profile 精确装配且对无关 gate 零加载，三家 harness 从同一真相源加载。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 目录原生单轨治理

- 目录结构必须直接表达 `AppRoot / L1 / L2 / L3`，不得维护人工索引或状态镜像。
- 规格、设计、metadata、代码与测试必须各自承担唯一职责，不得生成第二真相源。
- 长期未完成事项必须进入最低 owner 节点 `OPEN`；已解决事项转为当前要求或直接删除。

<a id="req-002"></a>
### REQ-002 命令与自然语言一致执行

- 显式调用工作流技能与自然语言意图必须使用同一 `RESOLVE / PRE / DURING / POST / HANDOFF` 五段执行契约；两者只在 RESOLVE 的输入方式上不同，产出同一 `(workflow, deliverable, scope)` 三元组。
- 工作流之间必须经 HANDOFF 交接：未决项必须落到「最低可关闭节点 `OPEN-###`」「Out of Scope」「下一工作流承接」三者之一；HANDOFF 必须声明唯一合法下游并覆盖其输入必需项，下一工作流的 RESOLVE 必须消费上一工作流的 HANDOFF，断链必须阻断。
- 轮次 HANDOFF 的物理形态是交接单：按需落 `.qwq_output/env/repo/runs/handoff/<轮次>/manifest.md`（宪法四项加证据字段「命令+退出码+时间戳+工作树 SHA」），由 `quwoquan_ops/gate/verify_handoff_manifest.py` 校验四项齐全、证据字段完整、未决项三向裁决零悬空。下游消费时证据过期即复跑，不得转抄结论。
- 各工作流完成判据以 `.agents/skills/review/references/completion-criteria.md` 为唯一判据表（完成 = 指定 verify 命令退出 0，禁止计数或抽样等代理指标），表存在性与各 SKILL.md HANDOFF 段引用由 `quwoquan_ops/gate/verify_agent_context_budget.py` 校验。
- 动态上下文、总览和变更报告只写入 `.qwq_output`。
- 目录、链接、章节、验收证据和禁止文件必须由可执行门禁校验。

<a id="req-003"></a>
### REQ-003 角色化评审与跨 harness 载体

- 评审必须由 `review` 工作流按 `(workflow, deliverable, profiles)` 从注册表派发角色执行：profile 由 changed_paths 与 deliverable 派生，未匹配 profile 的角色不派发，选中 bundle 内相同 gate 只执行一次。角色名以 `.agents/skills/review/references/roles/` 为唯一真相源，其他文件不得自行列举角色清单。
- Agent 上下文载体只允许顶层 Skill、role、checklist、reference 与 tool 五类，各有唯一职责。
- 顶层 Skill 只收录可独立触发、有输入、步骤、交付件和失败终态的完整工作流；原则、标准、检查项不得作为顶层 Skill 存在。
- role 定义评审或执行职责。
- checklist 只放带分级的可执行判定。
- reference 只放唯一 owner 的未分级知识。
- tool 只放该工作流独占的小工具。
- checklist 每条必须带 `MUST / MUST NOT / SHOULD / SHOULD NOT / MAY / ADVISORY` 分级；标 MUST 的条目必须绑定真实存在的 `gate:` 命令或客观可判定的 `check:` 谓词，否则必须降级为 SHOULD。
- 指令真相源必须放在三家 harness 共享载体（`AGENTS.md` 与 `.agents/skills/`）；harness 专属目录只允许放触发加速器与生成产物。
- 任一工作目录下 `AGENTS.md` 的合并总量必须落在最严 harness 的上下文预算内，超限必须阻断而不是静默截断。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 的仓库执行约束。
- 下游能力：仓库内所有业务节点、metadata、代码和测试。
- 读取事实：目录、Markdown、metadata、测试 `spec_ref` 与 Git diff。
- 写入事实：只修改正式规格、设计、metadata、代码和测试；派生结果写入 `.qwq_output`。
- 一致性要求：README 模板、命令和 gate 必须同步更新。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 目标节点可生成最小完整上下文

- GIVEN 仓库中存在符合层级规范的目标 spec 或被 L1 工程归属覆盖的代码路径。
- WHEN 开发者生成 feature context 并执行特性树门禁。
- THEN 输出包含唯一 owner、父链、要求、验收、设计决定、metadata、测试证据、OPEN 与 Git 影响。
- AND 任何人工索引、节点级 acceptance、changelog 或中央 backlog 回潮都会阻断。

<a id="sit-002"></a>
### SIT-002 轮次交接与完成判据机器可裁定

- GIVEN 一个完成任一工作流轮次并进入 HANDOFF 的会话。
- WHEN 轮次输出交接单且后继轮次的 RESOLVE 消费该交接单。
- THEN 交接单含宪法 HANDOFF 四项与证据字段（命令、退出码、时间戳、工作树 SHA）并通过校验门禁，未决项三向裁决零悬空。
- AND 各工作流的完成判据来自唯一判据表且为指定 verify 命令退出 0，证据过期时下游复跑而非转抄结论。

<a id="sit-003"></a>
### SIT-003 教训沉淀与并行会话合法合入

- GIVEN 交接单出现跨轮重复缺口或评审同类 finding 复发，且存在多个并行会话共用工作树。
- WHEN 触发 distill 沉淀提议并有会话申请合入。
- THEN 规则候选带触发场景、根因层、建议落点与 gate/check 绑定，经人确认后走 prd/dev 正常工作流落地。
- AND 合入按「scope-green + foreign-red 登记」裁定：本会话 scope 内门禁全绿、域外已知红已登记进交接单缺口段。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 全树证据引用收口

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：部分节点仍以同节点 OPEN 声明尚缺直接测试 `spec_ref`，影响自动验收覆盖率。
- 完成判定：`SIT-001` 及全部节点验收锚点均有真实测试 `spec_ref`，且不再依赖 OPEN 代替证据。

<a id="open-004"></a>
### OPEN-004 distill 沉淀工作流与资产垃圾回收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺教训沉淀工作流，同一教训跨会话重犯——「稳定规则写回 AGENTS.md」只是自觉条款，无工作流、无自动化、无审计（出处：调研转录 `0c4c608c-7219-47c2-bcda-5c66dcf93294`）。回写必须是「提议 + 人确认 + prd/dev 正常工作流」，agent 不得绕过工作流直接修改规则资产。
- 完成判定：`SIT-003` 的沉淀子句由真实工作流覆盖——新建 distill 顶层工作流技能（落位 .agents/skills/distill/，输入为交接单跨轮重复缺口、评审 finding 复发、用户同类纠正第二次出现，输出为带触发场景、根因层、建议落点、gate/check 绑定的规则候选，无绑定只能落 SHOULD/ADVISORY）并通过 `make verify-agent-context-budget`。资产垃圾回收报告（skill 死引用、harness 分叉、AGENTS.md 与特性树重复正文）可重复生成于 `.qwq_output`。

<a id="open-005"></a>
### OPEN-005 并行会话合法合入协议

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺并行会话的合法合入通道，并行脏树与 ContractGraph 互锁反复出现（出处：调研转录 `0c4c608c-7219-47c2-bcda-5c66dcf93294`，归纳计数「至少 8 会话」待精确复核），无静止窗口与合法合入通道时门禁正确变红反而逼出 `--no-verify`。
- 完成判定：`SIT-003` 的合入子句由真实 gate/check 覆盖——「scope-green + foreign-red 登记」合法合入态（本会话 scope 内门禁全绿、域外已知红登记进轮次交接单缺口段后允许合入）写入本节点能力要求并绑定 gate/check；ContractGraph accept 的静止窗口/原子 accept 约定有门禁化表达。
