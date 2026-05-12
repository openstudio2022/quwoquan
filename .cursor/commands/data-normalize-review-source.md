---
name: /data-normalize-review-source
id: data-normalize-review-source
category: Workflow
description: 归一化工作流 · 单来源自检反思阶段
---

## 目标

让编程助手对自己的提取结果做二次审视，重点排除：

- 并列点位误判为成员
- generic 名称误升为主实体
- 编号点位被无证据归父
- 文章内无关图片误选为内容图

## 输入

- `--extract-result`

## 真实实现

```bash
python3 quwoquan_data/tools/cli.py data normalize-build-review-input --extract-result "<extract-result.json>"
```

## 结构化检查

```bash
python3 quwoquan_data/tools/cli.py data normalize-validate-output --stage review --result "<review-result.json>"
```

## 输出

- `runtime/runs/<batch>/normalization/inputs/review/<source_ref>.json`
- `runtime/runs/<batch>/normalization/results/review/<source_ref>.json`

## 门禁 / 准出

- 必须符合 `source_review_result.schema.json`
- 必须显式输出 `selectedContentAssets` 与 `rejectedAssets`
- `needsAuthorityBackcheck` 必须明确

## 失败后动作

- 自检后仍不确定：进入 `/data-normalize-authority-source`
- 如存在明显证据不足：保留待审，不强行提升主实体

## Trace Keys

- `sourceUrl`
- `pageTitle`
- `extractResultPath`
