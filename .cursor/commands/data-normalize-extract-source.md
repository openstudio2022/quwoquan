---
name: /data-normalize-extract-source
id: data-normalize-extract-source
category: Workflow
description: 归一化工作流 · 单来源提取阶段
---

## 目标

让编程助手基于单来源 bundle 提取：

- `main_entity` 候选
- `members` 候选
- `aliases` 候选
- 图片语义分类与可引用判断

## 适用时机

- 已完成 `/data-source-fetch`
- 已有 `source.md` 与 `asset_manifest.json`

## 输入

- `--source-md`
- `--catalog-topic`
- `--catalog-name`
- `--batch-label`

## 真实实现

先准备结构化输入：

```bash
python3 quwoquan_data/tools/cli.py data normalize-build-extract-input \
  --batch-label "<batch>" \
  --source-md "<source.md>" \
  --catalog-topic "<topic_id>" \
  --catalog-name "<catalog name>"
```

然后由编程助手读取 input schema 并写出 result 文件。

## 结构化检查

```bash
python3 quwoquan_data/tools/cli.py data normalize-validate-output --stage extract --result "<result.json>"
```

## 输出

- `runtime/runs/<batch>/normalization/inputs/extract/<source_ref>.json`
- `runtime/runs/<batch>/normalization/results/extract/<source_ref>.json`

## 门禁 / 准出

- 必须符合 `source_extraction_result.schema.json`
- 图片必须区分 `content_photo` / `icon_logo` / `map_diagram` / `poster_cover` / `decorative` / `unknown`
- 必须显式给出 `watermarkStatusCandidate`

## 失败后动作

- schema 不通过：重新写 result 文件
- 语义不确定：允许进入下一阶段自检，但要保留 `uncertainItems`

## Trace Keys

- `sourceUrl`
- `pageTitle`
- `sourceMarkdownPath`
