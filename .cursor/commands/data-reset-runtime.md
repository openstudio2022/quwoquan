---
name: /data-reset-runtime
id: data-reset-runtime
category: Workflow
description: 数据工程 · 清理本地运行输出
---

## 目标

清理当前数据工程本地运行输出。当前只允许通过 `qwq-data reset`，不再调用
不存在的 `reset_quwoquan_data_runtime_full.sh`，也不恢复旧 `quwoquan_data/runtime/**`。

## 自然语言等价触发

用户说“清空数据运行态”“重置本地 data runtime”“删除生成输出重跑”时，按本命令语义执行。

## Spec Entry

- AppRoot Journey/Scenario：`runtime/system-architecture-and-engineering-guide`
- L1/L2/L3：按当前数据任务绑定。
- 验收意图：`SIT + contract`
- 测试证据：`local_contract`

## Pre-work Reflection

- 不删除 `quwoquan_data/publish/**`，除非用户明确要求并确认影响。
- 不删除 service/app/ops 输出。
- 输出根只认 `.qwq_output/**`。

## 当前实现

```bash
python3 quwoquan_data/scripts/cli.py reset
python3 quwoquan_data/scripts/cli.py reset --include-release
```

## 输出

- 清理摘要和后续需要重跑的任务列表。

## Exit Review

- 复跑 `python3 quwoquan_data/scripts/cli.py verify output-root-isolation`。
- 如仍有后台任务写入，必须先停止外部写入源再重试。
