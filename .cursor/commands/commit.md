---
name: /commit
id: commit
category: Workflow
description: 提交已完成的 Scenario slice 与对应 CR
---

> SDD 主流程：... → dev（已归档） → **commit** → deploy

`/commit` 的前置对象是：**已完成的 `L3_scenario` slice 与其对应 CR 范围**。

## 前置条件

- 四件套齐全
- `plan.yaml` 的目标 slice 已完成
- `acceptance.yaml` 无 `pending`
- `tests` 证据已回填
- `CR` 已完成本轮修订

## 提交前门禁

```bash
make gate
```

必要时按变更范围补充：

- Flutter tests
- service gate

## 提交行为

- git status
- git add
- git commit
- git push

## 输出

```text
提交完成：<feature-path>
L3_scenario: <scenario>
CR: <change-request>
下一步：/deploy
```
