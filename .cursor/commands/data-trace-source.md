---
name: /data-trace-source
id: data-trace-source
category: Workflow
description: 数据工程 · 发布产物与任务来源反查
---

## 目标

从 publish 路径片段或 taskId 反查来源、任务、批次和运行证据。当前入口是
`task trace`，不再使用已退役的 `data trace-source` 子命令。

## 自然语言等价触发

用户说“追查来源”“这条 source 从哪来”“这个发布物对应哪个任务”时，按本命令语义执行。

## Spec Entry

- AppRoot Journey/Scenario：`runtime/system-architecture-and-engineering-guide`
- L1/L2/L3：按当前数据任务绑定。
- 验收意图：`SIT + contract`
- 测试证据：`local_contract`

## Pre-work Reflection

- publish-first：以 `quwoquan_data/publish/**` 为发布真相源。
- runtime evidence：运行证据只从 `.qwq_output/local/data-runtime/**` 和 `.qwq_output/runs/data/**` 回查。
- 不补写缺失证据；缺失就是缺失。

## 当前实现

```bash
python3 quwoquan_data/scripts/cli.py task trace --ref "<publish-path-fragment>"
python3 quwoquan_data/scripts/cli.py task trace --task-id "<task-id>"
```

## 输出

- 反查摘要、任务/批次引用、publish 路径和必要的缺口说明。

## Exit Review

- 说明可追溯链路是否完整。
- 如果找不到来源，给出下一步应跑的 `task show/status` 或 `data download` 命令。
