---
name: /data-source-fetch
id: data-source-fetch
category: Workflow
description: 归一化工作流 · 单来源抓取与原始 bundle 落盘
---

## 目标

把单篇文章或单个图片页抓取为可复查的 source bundle：

- `page.html`
- `page.json`
- `page.text.txt`
- `source.md`
- `source_blocks.ndjson`
- `asset_manifest.json`

## 适用时机

- 已有具体 `sourceUrl`
- 需要后续做提取 / 自检 / 权威反查
- 需要稳定的原始 artifact，而不是直接让编程助手对 URL 即兴判断

## 输入

- `--batch-label`
- `--source-url`
- `--page-title`
- `--catalog-topic`
- `--catalog-name`
- `--source-type article|image`

## 真实实现

```bash
python3 quwoquan_data/tools/cli.py data source-fetch \
  --batch-label "<batch>" \
  --source-url "<url>" \
  --page-title "<page title>" \
  --catalog-topic "<topic_id>" \
  --catalog-name "<catalog name>" \
  --source-type article
```

## 结构化检查

```bash
python3 quwoquan_data/tools/cli.py data normalize-validate-output --stage fetch --result "<result.json>"
```

## 输出

- `runtime/runs/<batch>/normalization/source/bundles/<source_ref>/**`
- `runtime/runs/<batch>/normalization/inputs/fetch/<source_ref>.json`
- `runtime/runs/<batch>/normalization/results/fetch/<source_ref>.json`

## 门禁 / 准出

- fetch 结果必须通过 `source_bundle.schema.json`
- `source.md`、`source_blocks.ndjson`、`asset_manifest.json` 必须齐备

## 失败后动作

- 页面抓取失败：重试或更换来源 URL
- 图片抓取失败：保留页面 bundle，后续可单独补抓图片

## Trace Keys

- `sourceUrl`
- `pageTitle`
- `sourceMarkdownPath`
- `catalogTopicId`
