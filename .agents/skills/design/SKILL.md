---
name: design
description: Record the architecture decisions (DEC) needed to satisfy a frozen spec - object boundary, command/query split, testability of each decision, failure recovery with SLO and rollback. Use when the user says 设计方案, 梳理架构, 明确边界, 明确回滚, or 明确观测.
metadata:
  kind: workflow
  command: /design
---

# design

## 触发与输入

已冻结 spec 触发跨对象边界、命令/查询分流、并发一致性、恢复/回滚、SLO 或观测决策时使用。输入是 owner manifest、已冻结 REQ/验收、contracts 与现有 DEC。

## 执行

1. 只在达到设计门槛的 L2/L1 `design.md` 记录 DEC，声明决策、理由、被否决方案、约束/影响、关联要求/验收和影响 Story。
2. 明确 owner、command/query/event、一致性/幂等、失败终态、恢复动作、回滚、SLI/SLO、告警与测试 seam。
3. 功能事实保持在所属 Feature，wire 事实保持在 contracts；不把设计复制到 AGENTS、Review role 或 harness。
4. 运行 `make verify-feature-tree`，POST 按 `review` Skill 在命名 evidence 通过后派 Architect 主审与至多一名专审。

## 完成证据

DEC 能指回冻结 REQ/验收，每个决策有可执行测试 seam、typed 失败、恢复/回滚和观测结果；特性树与 POST Review 绑定当前指纹。

## 失败与停止

spec 未冻结、owner 冲突、contract 未定义、无法恢复/回滚或无法测试时 `GATE_BLOCK`，回 prd/explore。required evidence/Reviewer 不完整时不进 dev。

## 条件性交接

普通闭环交付 DEC、验证和未决项。只在跨会话、多人并行、外部阻断或证据复用时，持久化 owner、DEC/验收锨点、contract 摘要和指纹供 dev PRE 消费。
