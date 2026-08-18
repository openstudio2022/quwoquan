---
name: explore
description: Read-only workflow that locates where a change belongs before any code or spec is written - AppRoot Journey, L1/L2/L3 parent chain, scope, acceptance intent, parallel-session conflicts. Use at the start of any non-trivial change, and when the user says 先分析, 看归属, 怎么拆, 有哪些风险, or where does this go.
metadata:
  kind: workflow
  command: /explore
---

# explore

只读定位增量的产品归属、父链、边界与风险。**不写代码，也不写规格。**
五段执行契约见根 `AGENTS.md`。

## 触发

- 显式命令 `/explore`。
- 自然语言：先分析、看归属、怎么拆、有哪些风险，或任何无法唯一 RESOLVE 的非平凡需求。

## 输入

- 用户意图描述（必需；连 Journey 都定位不到时先向用户澄清，不凭猜测往下走）。
- 候选代码 / spec 路径（可选）。
- 当前 Git 影响面（`git status`，必需）。

## 角色

主会话扮演 **domain-locator**（只读定位者）：只定位与提问，不做产品、架构或实现决定。

## 执行

自由度：高（文本指导，路径由目标决定）。

1. 读最近的 `AGENTS.md` 与 [`specs/feature-tree/README.md`](../../../specs/feature-tree/README.md)。
2. 已知路径时 `make feature-context TARGET=<path>`；否则从 AppRoot Journey 与 L1 边界逐层定位。
3. 判断触发面：metadata、runtime error、Mock 隔离、页面质量、Data/Service/App、观测、环境与回滚。
4. 用 `git status` 找出脏工作树中并行会话改动与目标路径的交集，列出受影响的棘轮基线（ceiling 类门禁）当前值。
5. 读目标父链的 `OPEN`。
6. 意图含糊或存在多个待裁决分叉时，按 [references/decision-tree-interview.md](references/decision-tree-interview.md) 建决策树、按 frontier 分轮提问；事实自己查（可派子代理），决策才问用户。

- [MUST NOT] 回滚、覆盖或清理与本目标无关的用户改动。**脏工作树是常态。**
- [MUST NOT] 扫描或创建中央台账——本仓库不存在中央台账。

## 交付件

**RESOLVE 报告**：唯一 `(workflow, deliverable, scope)`、完整父链、In/Out Scope、验收意图
`UAT/DOM/SIT/GWT/contract`、证据层 `local_contract/api_integration/user_acceptance`、
直接依赖、风险与下游 PRE 输入。

送审前自检：

- 无 TBD 占位；
- 决策树 frontier 已清空，或残项显式列为风险；
- 代码 owner 唯一，父子规格无冲突，验收意图可观察。

## 内置评审

- POST：调 `review`（workflow=`explore`，segment=POST，deliverable=`resolve-report`），
  典型角色 product + architect，只校验归属唯一与范围完整，无 gate 执行。

## 失败与停止

- 代码 owner 缺失或被多个 L1 同优先级认领：`GATE_BLOCK`，先修规格归属。
- 父子规格冲突、验收意图不可观察：`GATE_BLOCK`。
- 不做 PRD、DEC 或实现。

## HANDOFF

- **产出物**：RESOLVE 报告。
- **未决项去向**：已知 OPEN 清单、并行冲突风险、受影响棘轮当前值。
- **唯一合法下游**：`prd`（纯查询任务直接答复用户，不交接）；RESOLVE 报告必须覆盖 `prd` 输入段全部必需项。
- **证据链**：`make feature-context` 输出、`git status` 交集结论。
