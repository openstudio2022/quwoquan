---
name: /prd
id: prd
category: Workflow
description: 需求规格基线（面向 L3_story，先冻结商用要求）
---

> SDD 主流程：explore → **prd** → design → dev → commit → deploy

## PRD Gate

进入 `/prd` 前必须确认：

- 已定位 `L1_capability`
- 已确定目标 `L2_feature`
- 已确定目标 `L3_story`
- `A1~An` 可量化并映射 `T1~T4`
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

`/prd` 只创建或更新 `L3_story`，不创建第四层或第五层节点。

## 产出

- `spec.md`
- `acceptance.yaml`
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

- `feature`
- `level: L3_story`
- `execution`
- `level_acceptance`

每条核心验收项必须可映射到 `T1~T4`，商业上线 blocker 必须单独写成可判定验收项。

## 结束输出

```text
PRD 完成：<feature-path>
L1: <capability>
L2: <feature>
L3: <story>
下一步：/design
```
