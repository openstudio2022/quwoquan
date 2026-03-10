---
name: /deploy
id: deploy
category: Workflow
description: 部署并执行 T3/T4 验证
---

> SDD 主流程：commit → **deploy**

`/deploy` 不再使用 `L3/L4` 表示测试层。

## 部署链路

1. 部署到 integration / staging
2. 执行 `T3` 端云集成验证
3. 执行 `T4` 端到端旅程验证
4. 满足 SLO 与回滚条件后进入生产放量

## 验证口径

- `T3`：API contract、真实存储、集成环境验证
- `T4`：Patrol / 真机 / 系统能力 / 关键旅程验证

## 输出

```text
部署完成：<feature or release>
T3: PASS/FAIL
T4: PASS/FAIL
```
