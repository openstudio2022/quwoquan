# 双批真实联网 E2E 稳定性规格

## 1. 目标

用两次真实联网全 DAG 跑通，证明同一任务在不同批次之间具备：

- 目录结构同构。
- 成品资产零交集。
- 质量不回退。
- 批次号单调递增且可追溯。

## 2. 批次角色

| 角色 | batch_id | 说明 |
|---|---|---|
| 基线批 A | `e2e_baseline` | 首次全 DAG 成功后冻结 baseline snapshot |
| 稳定性批 B | `e2e_stability_2` | 新批次，`globalBatchSeq(B) = globalBatchSeq(A) + 1` |

## 3. 运行模式

- 必须使用 `online_live`。
- 必须跑完整 DAG，不得只跑到 `1.download` 或局部 checkpoint。
- 禁止用合成图、假图或只跑样例布局替代真实验证。

## 4. 每阶段准出

### 4.1 download_plan

- `source_plan.json` 至少 2 条可消费 source。
- source platform 命中来源类目表。

### 4.2 download_fetch

- 来源单元落在批次级 `sources/{sourceUnitId}/`，对象只保存 `1.download/source_refs.json` 软引用。
- 图片通过下载门、像素门、相关性门、版权门。

### 4.3 build_homepage

- 实体主页三件套齐全。
- `page.md`、`_entity.json`、`manifest.json` 均存在。
- 主页正文不是占位或模板拼接。

### 4.4 produce_plan / produce_compose / produce_author / produce_review

- 产出 writing pack、prompt、草稿、审校结果。
- 仅 `generator=agent` 的草稿可进入交付面。
- `reviewDecision=approved` 才可 materialize。

### 4.5 ship

- 发布包与对象根同构。
- 成品资产文件名即 `assetId`。

## 5. baseline snapshot 契约

baseline snapshot 记录以下最小字段：

- `globalBatchSeq`
- `coverageEntities`
- `contentRefs`
- `directoryTree`（相对 batch 根，资产文件名归一化）
- `perEntity`：`sourceUnitCount`、`downloadImageCount`、`pageChars`、`homepageAssetCount`
- `perPost`：`postArticleChars`、`postAssetCount`、`reviewDecision`
- `assetIds`
- `gateResults`

## 6. 比对规则

### 6.1 必须一致

- 目录树归一化后一致。
- `coverageEntities` 一致。
- `contentRefs` 一致。
- 实体对象集合一致。
- 文章对象集合一致。
- `globalBatchSeq(B) = globalBatchSeq(A) + 1`。

### 6.2 不得回退

- `sourceUnitCount` 不得下降。
- `downloadImageCount` 不得下降。
- `pageChars` 不得低于 baseline 的 90%。
- `homepageAssetCount` 不得下降。
- `postArticleChars` 不得低于 baseline 的 90%。
- `postAssetCount` 不得下降。
- `reviewDecision` 必须保持 `approved`。

### 6.3 零交集

- baseline 与 candidate 的 `assetIds` 集合不得相交。

## 7. 稳定性报告

稳定性报告至少包含：

- 两个 batch 的 `globalBatchSeq` 证据。
- 逐阶段 PASS/FAIL。
- 目录同构结论。
- 质量非回退结论。
- 跨批 assetId 零交集结论。

报告文件：

- `batches/e2e_stability_2/_shared/e2e_stability_report.md`

## 8. 验收门

- `python3 quwoquan_data/scripts/cli.py verify batch-stability --task ... --baseline ... --candidate ...`
- `python3 quwoquan_data/tests/common/test_batch_asset_stability.py`
