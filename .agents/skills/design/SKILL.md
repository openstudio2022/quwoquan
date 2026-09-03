---
name: design
description: Record the architecture decisions (DEC) needed to satisfy a frozen spec - object boundary, command/query split, testability of each decision, failure recovery with SLO and rollback. Use when the user says 设计方案, 梳理架构, 明确边界, 明确回滚, or 明确观测.
metadata:
  kind: workflow
  command: /design
---

# design

## 触发与输入

已冻结 spec 需要对象边界、命令/查询分流、并发一致性、恢复/回滚、SLO 或观测决策时使用。输入是用户目标、plan/diff、已知路径与冻结验收；调用前不要求 owner manifest。角色交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.design`，可见输出由 canonical projector 生成。

## 执行

1. PRE 从用户目标、plan/diff 与已知路径确定 exact target；读取最近子树 `AGENTS.md`，运行默认 compact `make feature-context TARGET=<exact-path>`，保存 stdout 的 immutable exact ref 后加载冻结 REQ、验收、contracts 与现有 DEC。
2. 只在达到设计门槛的 L2/L1 `design.md` 记录 DEC，包含决策、理由、被否决方案、约束/影响、关联要求/验收和影响 Story。
3. 明确 owner、command/query/event、一致性与幂等、typed 失败、恢复、回滚、SLI/SLO、告警和测试 seam；功能事实与 wire 事实保留在各自 owner。
4. 运行 `make verify-feature-tree`；POST 复用 PRE owner identity ref，并生成 current candidate evidence predecessor，报告命名 evidence 结果；默认零 Reviewer，只在用户显式 `/review` 或进入 lane→`dev1.0` PR / handoff 准出时有界评审。

## 完成证据

DEC 能指回冻结验收，每个决策都有可执行测试 seam、失败恢复、回滚与观测结果；immutable ref 与门禁绑定当前工作树，未评审时如实标注。

## 失败与停止

spec 未冻结、target/owner 冲突、contract 未定义、无法恢复/回滚或无法测试时 `GATE_BLOCK`，回 prd/explore；required evidence 不完整时不进 dev。

## 条件性交接

设计冻结后向 dev 传递 exact target、immutable ref、DEC 与验收；只有 canonical 六类 handoff 触发成立时持久交接。
