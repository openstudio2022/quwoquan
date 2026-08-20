# L2 Design：开发流程治理 (`development-workflow-governance`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收”需要 `directory-native-sdd` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`directory-native-sdd`](./directory-native-sdd/spec.md)：工具必须直接扫描目录与 Markdown；删除 `.qwq_output` 后仍可从受版本控制真相源重建上下文。
- [`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)：顶层 Skill 只收录完整工作流，评审按 profile 精确装配，三家 harness 同源加载。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 的仓库执行约束。
- 下游能力：仓库内所有业务节点、metadata、代码和测试。
- 读取事实：目录、Markdown、metadata、测试 `spec_ref` 与 Git diff。
- 写入事实：只修改正式规格、设计、metadata、代码和测试；派生结果写入 `.qwq_output`。
- 一致性要求：README 模板、命令和 gate 必须同步更新。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 目录结构和父子 spec 构成唯一特性树
- 决策：目录结构和父子 spec 构成唯一特性树。
- 理由：让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`directory-native-sdd`](./directory-native-sdd/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 顶层 Skill 工作流准入与 PRD/Design 分段边界
- 决策：`.agents/skills/` 顶层只收录可独立触发、有输入、步骤、交付件和失败终态的完整工作流，全部套用统一八段模板（触发/输入/角色/执行/交付件/内置评审/失败与停止/HANDOFF）。
- 命令映射：有 Cursor 命令的工作流与命令双向一一对应。
- PRD/Design 边界：`prd` 拥有 `spec.md`、范围与可测试验收；`design` 只在达到设计门槛时拥有 DEC、对象边界、失败恢复与回滚，PRD 的 HANDOFF 允许无设计变化时跳过 design 直达 dev。
- 理由：原则、标准和检查项作为顶层 Skill 会占用自动发现预算却没有独立输入与输出；PRD 与 Design 合并会把 product 与 architect 的职责与评审混为一体。
- 被否决方案包括把领域原则暴露为顶层 Skill、把 extend/verify/deliver 保留为独立入口，以及引入 tracked workflow manifest 做第二真相源。
- 约束与影响：原则页只能作为唯一 owner 角色的 reference 存在。
- 子流程归属：`extend` 是 `dev` 的条件子流程。
- 验证归属：`verify` 的证据生成与评价统一进入每个工作流 POST 自动调用的 `review`。
- 关联要求：`REQ-003`
- 影响 Story：DEC-002 与 DEC-003 共同影响 [`agent-skill-review-context-organization`](./agent-skill-review-context-organization/spec.md)
- 关联验收：`SIT-001`

<a id="dec-003"></a>
### DEC-003 review bundle 的 profile 装配与 gate 证据去重
- 决策：评审注册表以工作流名为第一级键，先由 changed_paths 与 deliverable 派生 profile，再按 `when` 条件装配角色的 base + profile checklist bundle。
- 派发边界：未匹配 profile 的角色不派发。
- 证据复用：选中 bundle 内相同 gate 命令去重执行一次，evidence 映射共享给多个 reviewer。
- 双向一致性：每个工作流 SKILL.md 的内置评审段与注册表 binding 双向一致。
- 理由：无条件角色并集导致纯 Go 或 Python 改动仍运行大量 Flutter gate；同一 gate 被多个角色重复执行浪费且证据不一致。
- 被否决方案包括按 `(stage, deliverable)` 无条件并集派发、用 suppress 补丁做减法，以及由各 reviewer 自行重跑 gate。
- 约束与影响：registry 中每个 binding 与 checklist 必须双向可达。
- Reviewer 输入边界：reviewer 只拿交付件与显式文件路径，不共享实现会话推理。
- 证据失败边界：evidence 缺失或失败不得包装为通过。
- 关联要求：`REQ-003`
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 门禁必须可重复、输出精确文件和原因，并在仓库规模下保持秒级目录扫描。
- 报告记录节点数、规格/设计数、问题分类和未归属变更，不记录敏感内容。
