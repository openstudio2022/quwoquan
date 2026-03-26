---
name: /prd
id: prd
category: Workflow
description: 需求规格基线（面向 Journey / Scenario，先冻结商用要求）
---

> SDD 主流程：explore → **prd** → design → dev → commit → deploy
> 需求已非常明确且方案已收敛时，可直接使用 `/baseline` 一次完成规格与设计基线。

## PRD Gate

进入 `/prd` 前必须确认：

- 已定位 `L1_capability`
- 已确定目标 `L2_journey`
- 已确定目标 `L3_scenario`
- `journey_acceptance` / `scenario_acceptance` 可量化并映射 `T1~T4`
- 范围边界与 Out of Scope 清晰
- 已识别对标输入或明确无需对标
- 已冻结不可打折的交互基线
- 已明确 `SLO/KPI`、弱网、并发、性能、容量目标
- 若涉及权限、小趣、可见性、删除撤销：已冻结权限边界、保留策略与撤销时效
- 若涉及创作、编辑、升级、删除、分享：已冻结数据生命周期合同
- 若与已有 Story 重叠：已冻结覆盖矩阵与优先级
- 若可灰度上线：已冻结迁移方案、feature flag、观测指标与回滚条件
- 若涉及 `path / operation / surface / route / decoder context`：已明确 metadata 唯一真相源
- 若涉及助手链路：已阅读 `quwoquan_app/personal_assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`，并明确本次需求不会通过 runtime 垂类特判或字符串硬编码落地

任一未满足：

```text
GATE_BLOCK（PRD 准入未满足）
```

## 执行对象

`/prd` 创建或更新 `L2_journey`、`L3_scenario` 的规格与验收，并创建或续写对应 `CR`。

若确认本次需求无需拆成两轮评审，也可改走 `/baseline`。

## 产出

- `spec.md`
- `acceptance.yaml`
- `specs/changelog/CR-*.yaml`
- 商用基线：`SLO/KPI`、权限边界、生命周期、覆盖矩阵、迁移灰度回滚

## `spec.md` 要求

必须包含：

- 背景与动机
- 目标用户
- 功能范围
- Out of Scope
- 约束
- 对标输入与吸收结论
- 角色分工
- 既有 Story 覆盖矩阵
- 数据生命周期合同
- 小趣/权限/分享边界
- 非功能目标
- 迁移、灰度与回滚要求
- 验收重点

若涉及助手，还必须补充：

- 影响层：runtime / skill / tool / prompt / UI
- 对应真相源与场景级设计文档
- 明确哪些能力必须落在 asset / metadata / config，而不是 runtime

## `acceptance.yaml` 要求

必须包含：

- `version`
- `feature`
- `level`
- `execution`
- `scope`
- `journey_acceptance` 或 `scenario_acceptance`

要求：

- `L2_journey`：主要冻结端到端旅程、跨 Scenario 组合规则、发布 guardrails
- `L3_scenario`：主要冻结单环节场景、异常边界、路径覆盖与最小可实施范围
- 每条核心验收项必须可映射到 `T1~T4`
- 商业上线 blocker 必须单独写成可判定验收项

## `CR` 要求

若本次变更影响行为、边界或验收，必须创建或续写：

- `specs/changelog/CR-YYYYMMDD-NNN-<slug>.yaml`

CR 至少要记录：

- `affected_nodes`
- `revision`
- `changed_documents`
- `impact`

## 结束输出

```text
PRD 完成：<feature-path>
L1: <capability>
L2: <journey>
L3: <scenario>
CR: <change-request>
下一步：/design
```
