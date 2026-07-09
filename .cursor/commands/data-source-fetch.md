---
name: /data-source-fetch
id: data-source-fetch
category: Workflow
description: 数据工程 · 当前批次来源下载与 source bundle 补齐
---

## 目标

把指定任务/批次/实体的 homepage、article、image 来源下载回当前数据任务主干。
不再使用已退役的 `data source-fetch` 子命令，也不手写旧 `runtime/runs/**` 路径。

## 自然语言等价触发

用户说“抓这个来源”“补 source.md/asset manifest”“下载这个实体主页来源”时，按本命令语义执行。

## Spec Entry

- AppRoot Journey/Scenario：`runtime/system-architecture-and-engineering-guide`
- L1/L2/L3：按当前数据任务绑定。
- 验收意图：`SIT + contract`
- 测试证据：`local_contract + api_integration`

## Pre-work Reflection

- data CLI-first：只使用 `python3 quwoquan_data/scripts/cli.py`。
- 权利与来源：不绕过 source registry、license policy 或 same-source image gate。
- 输出边界：运行态只写 `.qwq_output/local/data-runtime/**`。

## 当前实现

```bash
python3 quwoquan_data/scripts/cli.py data download \
  --task "<task-id>" \
  --batch "<batch-id>" \
  --entity-ids "<entity-a>,<entity-b>" \
  --entity-type "景区" \
  --lane homepage
```

## 输出

- source plan、source unit、asset manifest 等运行证据位于 `.qwq_output/local/data-runtime/**`。
- 发布真相源仍只位于 `quwoquan_data/publish/**`。

## Exit Review

- 说明下载 lane、实体范围、成功/失败列表。
- 运行 `python3 quwoquan_data/scripts/cli.py verify output-root-isolation`。
- 如存在反爬、无授权图或 sourceUnavailable，必须单独列明，不混入成功结果。
