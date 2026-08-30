# 自修循环（跨阶段通用）

任一阶段完成判据失败时的唯一处置循环，取代「盲试后放弃」与「一票 manual_required」。

## 循环

```text
跑完成判据命令 → 读结构化 issue（stderr/报告文件） → 定位被点名的产物文件
→ 修产物（只改本阶段输出目录内的文件） → 复跑判据命令
```

- 每阶段自修 ≤3 轮；轮数记入 receipt `evidence.repairRounds`。
- 每轮必须针对具体 issue 修改具体文件；不允许无差别重跑同一命令期待不同结果。
- 修复根因属于前序阶段产物时：停止本阶段自修，receipt `verdict=blocked`、
  `openItems` 登记 `return_to_stage` 及目标阶段，由下一轮会话回到该阶段处理。

## MUST NOT

- [MUST NOT] 修改 `quwoquan_data/scripts/verify/**`、`quwoquan_data/schema/**`
  或任何门禁参数、阈值、allowlist 来让判据通过。
- [MUST NOT] 删除、改写或补写 receipt、execution_state、来源/权利/评审证据。
- [MUST NOT] 用 fixture、历史数据或估算结果顶替真实产物。

## 超限动作

3 轮后判据仍失败：

1. 调 `task stage-record` 落 `verdict=blocked` receipt，`openItems` 带全部未决 issue。
2. 向用户返回带 `executionId`、阶段名与 issue 原文的 `GATE_BLOCK`。
3. 不再重试；恢复入口统一走 [recovery.md](recovery.md)。
