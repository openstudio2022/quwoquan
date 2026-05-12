---
name: /data-build-entities-tags
id: data-build-entities-tags
category: Workflow
description: 应用数据生成工作流 · 生成实体和标签阶段
---

## 目标

生成：

- 地理目录候选层 `catalog.ndjson`
- `tag_catalog`
- `entity_catalog`

## 真实实现

推荐：

```bash
python3 quwoquan_data/tools/cli.py data build-entities-tags --catalog-config "<geo_catalog_config.yaml>" --catalog-output "<runtime/seed/catalog.ndjson>"
```

或对已有目录直接构建：

```bash
python3 quwoquan_data/tools/cli.py data build-entities-tags --catalog "<runtime/seed/catalog.ndjson>"
```

## 内部原语

- `build_geo_poi_catalog`
- `crawl tag-catalog-build`
- `crawl entity-catalog-build`

## 门禁

- `label_zh` 覆盖率
- `entityId` 无重复
- `tagRefs` 可解析
- 目录候选层到实体层映射抽样通过
