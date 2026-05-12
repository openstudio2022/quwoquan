---
name: /data-entity-catalog-materialize
id: data-entity-catalog-materialize
category: Workflow
description: 归一化工作流 · 物化 entity_catalog
---

## 目标

把 `entity_resolution.ndjson` 物化为 `entity_catalog` 可消费的实体行。

## 输入

- `--batch-label`
- `--catalog`
- `--output-name`

## 真实实现

```bash
python3 quwoquan_data/tools/cli.py data entity-catalog-materialize \
  --batch-label "<batch>" \
  --catalog "<catalog.ndjson>" \
  --output-name "normalized_entities.ndjson"
```

## 输出

- `runtime/seed/entity_catalog/<output-name>`

## 门禁 / 准出

- 只能消费 `entity_resolution.ndjson`
- 不允许直接从 raw catalog 跳过编译写实体表

## Trace Keys

- `batchLabel`
- `catalogPath`
- `entityCatalogPath`
