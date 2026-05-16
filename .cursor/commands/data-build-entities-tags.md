---
name: /data-build-entities-tags
id: data-build-entities-tags
category: Workflow
description: 应用数据生成工作流 · 实体/标签构建与归一化全阶段
---

## 目标

构建和归一化实体与标签体系，支持以下 `--phase` 阶段：

| phase | 说明 |
|-------|------|
| `all`（默认） | catalog + entity-tag 一步完成 |
| `catalog` | 仅构建地理目录候选层 `catalog.ndjson` |
| `entity-tag` | 从 catalog 生成 `entity_catalog` + `tag_catalog` |
| `normalize-prepare` | 准备编程助手归一化输入 + 生成任务清单 |
| `normalize-validate` | 验证编程助手结果是否存在且 schema 合规 |
| `compile` | 编译归一化结果为规范化实体目录 |
| `materialize` | 物化到正式 `entity_catalog/entities.ndjson` |

## 工作流位置

`data explore` → `data baseline` → **data build-entities-tags** → `data download` → normalize 阶段 → `data process-content` → `data publish`

## 常用调用

```bash
# 全量构建（catalog + entity-tag）
python3 quwoquan_data/tools/cli.py data build-entities-tags \
  --catalog-config "<config.yaml>" --catalog-output "<catalog.ndjson>"

# 准备归一化任务清单
python3 quwoquan_data/tools/cli.py data build-entities-tags \
  --phase normalize-prepare --spec "<spec.yaml>" --batch-label "<batch>"

# 验证编程助手结果（单阶段）
python3 quwoquan_data/tools/cli.py data build-entities-tags \
  --phase normalize-validate --batch-label "<batch>" --stage extract

# 编译 + 物化
python3 quwoquan_data/tools/cli.py data build-entities-tags \
  --phase compile --batch-label "<batch>"
python3 quwoquan_data/tools/cli.py data build-entities-tags \
  --phase materialize --batch-label "<batch>" --catalog "<catalog.ndjson>"
```

## 编程助手归一化流程

1. `--phase normalize-prepare` 生成 `assistant_tasks/extract.json` 任务清单
2. 编程助手读取任务清单，逐条执行 extract → review → authority → escalate
3. 每个阶段完成后用 `--phase normalize-validate` 校验结果
4. 全部阶段完成后 `--phase compile` + `--phase materialize`

## 门禁

- `entityId` 无重复
- `tagRefs` 可解析
- `quwoquan_data/scripts/verify/verify_geo_catalog_quality.py` 通过
- `quwoquan_data/scripts/verify/verify_catalog_entity_consistency.py` 通过
