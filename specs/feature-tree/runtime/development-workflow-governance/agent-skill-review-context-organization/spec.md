# L3 Story：Agent 技能与评审上下文组织 (`agent-skill-review-context-organization`)

> 所属能力：[开发流程治理](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；支撑全部 Scenario 的一致实施与审核约束
>
> 设计归属：[L2 DEC-002](../design.md#dec-002)、[L2 DEC-003](../design.md#dec-003)

## 1. 用户价值

作为编程 Agent 或审核者，我希望顶层技能只描述可执行的完整工作流、评审只装配与改动影响面匹配的检查项，从而在 Cursor / Codex / Claude Code 任一 harness 中都以最小上下文获得同一套准入、执行与准出约束。

## 2. 范围与非目标

### In Scope

- `.agents/skills/` 顶层工作流技能的准入、统一八段模板与命令映射。
- 评审注册表按 `(workflow, deliverable, profiles)` 的条件装配、gate 去重与可达性。
- 原则页迁入唯一 owner 角色 reference；命令薄壳只描述当前执行入口。

### Out of Scope

- 各业务领域自身的规格内容与 gate 实现细节。
- tracked workflow manifest、技能状态台账或评审历史记录。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 工作流技能统一模板

- 顶层 SKILL.md 必须 `metadata.kind: workflow` 且八段齐全（触发/输入/角色/执行/交付件/内置评审/失败与停止/HANDOFF）。
- 交付件与内置评审段不得为空。
- HANDOFF 必须声明唯一合法下游。

<a id="req-002"></a>
### REQ-002 命令与技能双向映射

- 声明 `metadata.command` 的技能必须存在同名 `.cursor/commands/*.md` 薄壳，反向亦然；薄壳只描述当前执行入口，不含历史、迁移或多 harness 说明。

<a id="req-003"></a>
### REQ-003 profile 精确派发

- 评审装配必须先由 changed_paths 与 deliverable 派生 profile，再按条件选择角色 checklist。
- 未匹配 profile 的角色与 gate 不得加载。
- 选中 bundle 内相同 gate 只执行一次。

## 4. 契约引用

- 上下文门禁：`quwoquan_ops/gate/verify_agent_context_budget.py`
- 注册表：`.agents/skills/review/references/registry.yaml`
- 派发装配唯一执行体：`quwoquan_ops/cli/review_dispatch.py`（派发清单与去重 gate 计划落 `.qwq_output/env/repo/runs/review/`）
- 子代理生成器：`quwoquan_ops/tools/generate_codex_agents.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 命令薄壳与技能一一对应

- GIVEN `.cursor/commands/` 与 `.agents/skills/` 处于当前态。
- WHEN 门禁校验命令映射与薄壳措辞。
- THEN 每个命令有同名 workflow 技能且反向唯一；薄壳含历史或迁移叙述、或存在无技能对应的命令时被阻断。

<a id="gwt-002"></a>
### GWT-002 顶层只有完整工作流技能

- GIVEN `.agents/skills/` 顶层目录。
- WHEN 门禁校验每个技能的 frontmatter 与章节结构。
- THEN 全部技能 `metadata.kind: workflow` 且八段齐全；原则、标准或检查项出现在顶层时被阻断。

<a id="gwt-003"></a>
### GWT-003 PRD 可条件跳过 Design

- GIVEN 一次未达到设计门槛的规格增量。
- WHEN `prd` 完成 POST 评审并交接。
- THEN HANDOFF 的合法下游允许直达 `dev` 而不经 `design`；达到门槛时必须先经 `design`。

<a id="gwt-004"></a>
### GWT-004 无关 gate 零加载

- GIVEN 一次只触及单一技术栈的改动（如纯 Go contract 或纯 Python gate）。
- WHEN 评审注册表按 changed_paths 派生 profile 并装配 bundle。
- THEN bundle 只含匹配 profile 的角色 checklist，并满足以下约束。
  - 不匹配技术栈的 gate 不出现在证据计划中。
  - 相同 gate 在计划内只出现一次。
  - 含 `<...>` 占位符的参数化 gate 与可直跑 gate 分列两字段，执行方绑定实参后执行或显式判 N/A，不得混排派发。

<a id="gwt-005"></a>
### GWT-005 三家 harness 同源一致

- GIVEN `.agents/skills/` 真相源、`.claude/skills` 符号链接与 `.codex/agents` 生成物。
- WHEN 三家 harness 分别发现技能与 reviewer 子代理。
- THEN 加载到同一正文；生成物与真相源漂移或符号链接断裂时门禁阻断。

## 6. 依赖

- 前置要求：根 `AGENTS.md` 五段执行契约与 [`directory-native-sdd`](../directory-native-sdd/spec.md) 的目录原生规则。
- 上游事实：`.agents/skills/**`、`.cursor/commands/**`、注册表与 Git diff。
- 下游结果：评审 bundle、gate 证据计划或 GATE_BLOCK。
- 父级设计：`DEC-002`、`DEC-003`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 工作流技能与精确派发尚未形成直接测试证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：顶层技能统一模板、命令双向映射、profile 精确派发与三家 harness 同源加载全部由门禁与 local_contract 测试绑定。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003`、`GWT-004`、`GWT-005` 均有真实门禁或 local_contract 测试 `spec_ref`，且不再依赖本 OPEN 代替证据。
