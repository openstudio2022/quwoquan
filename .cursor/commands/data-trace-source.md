---
name: /data-trace-source
id: data-trace-source
category: Workflow
description: 归一化工作流 · 单来源全链路追查
---

## 目标

按来源 URL、页面标题、`source.md` 路径追查它在归一化工作流中的全部文件引用。

## 输入

- `--batch-label`
- `--source-ref` 或 `--source-md` 或 `--source-url`

## 真实实现

```bash
python3 quwoquan_data/tools/cli.py data trace-source \
  --batch-label "<batch>" \
  --source-md "<source.md>"
```

## 输出

- `runtime/runs/<batch>/normalization/compiled/trace/<source_ref>.json`

## 门禁 / 准出

- 至少能定位 extract / review / authority 三阶段结果路径

## 失败后动作

- 若找不到来源：先检查 `/data-source-fetch` 是否成功落盘

## Trace Keys

- `sourceUrl`
- `pageTitle`
- `sourceMarkdownPath`
