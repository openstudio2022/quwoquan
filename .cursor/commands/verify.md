---
name: /verify
id: verify
category: Quality
description: 验证 L3_story 完成度、测试证据与门禁状态
---

> SDD 主流程：... → dev → **verify** / commit → deploy

`/verify` 只验证：

- `L3_story` 是否完成
- `Task` 是否收口
- `acceptance.yaml` 是否闭环
- `T1~T4` 证据是否存在

## 核查项

- 四件套是否齐全
- 当前交付任务是否都已完成
- `acceptance.yaml` 是否无 `pending`
- `implemented` 项是否有 `tests`
- 是否仍残留旧层级

## G3

```bash
make gate-full
```

## 输出

```text
验证报告：<feature-path>
L3_story: <story>
BLOCKING: <N>
WARNING: <N>
```
