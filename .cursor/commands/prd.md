---
name: /prd
id: prd
category: Workflow
description: 需求规格基线（面向 L3_story）
---

> SDD 主流程：explore → **prd** → design → dev → commit → deploy

## PRD Gate

进入 `/prd` 前必须确认：

- 已定位 `L1_capability`
- 已确定目标 `L2_feature`
- 已确定目标 `L3_story`
- 至少有 3 条可测量验收项
- 范围边界与 Out of Scope 清晰
- 已说明 `T1~T4` 责任
- 已识别对标输入或明确无需对标

任一未满足：

```text
GATE_BLOCK（PRD 准入未满足）
```

## 执行对象

`/prd` 只创建或更新 `L3_story`，不创建第四层或第五层节点。

## 产出

- `spec.md`
- `acceptance.yaml`

## `spec.md` 要求

必须包含：

- 背景与动机
- 目标用户
- 功能范围
- Out of Scope
- 约束
- 对标输入与吸收结论
- 角色分工
- 非功能目标
- 验收重点

## `acceptance.yaml` 要求

必须包含：

- `feature`
- `level: L3_story`
- `execution`
- `level_acceptance`

每条核心验收项必须可映射到 `T1~T4`。

## 结束输出

```text
PRD 完成：<feature-path>
L1: <capability>
L2: <feature>
L3: <story>
下一步：/design
```
