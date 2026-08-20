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

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 全树证据引用收口

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：部分节点仍以同节点 OPEN 声明尚缺直接测试 `spec_ref`，影响自动验收覆盖率。
- 完成判定：`SIT-001` 及全部节点验收锚点均有真实测试 `spec_ref`，且不再依赖 OPEN 代替证据。
