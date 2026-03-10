---
name: /commit
id: commit
category: Workflow
description: 提交已完成的 L3_story
---

> SDD 主流程：... → dev（已归档） → **commit** → deploy

`/commit` 的前置对象只有一个：**已完成并归档的 `L3_story`**。

## 前置条件

- 四件套齐全
- 当前 Task 已完成
- `acceptance.yaml` 无 `pending`
- `tests` 证据已回填
- `tree_index.yaml` 状态已完成

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
L3_story: <story>
下一步：/deploy
```
