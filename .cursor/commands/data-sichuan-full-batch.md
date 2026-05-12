---
name: /data-sichuan-full-batch
id: data-sichuan-full-batch
category: Workflow
description: 四川县级切片目录千级重建、门禁、全量 skip-hydrate 与分批深 publish
---

## 目标

- `geo_catalog_config.sichuan.county.yaml` + Overpass 重建 `sichuan_chuanxi_attractions_catalog.ndjson`
- `verify_geo_catalog_quality --min-kept/--min-rows` + `verify_catalog_entity_consistency`
- `spec-build` 全量 topic → `data download --skip-hydrate` → 按批 `data download`（仅 hydrate）/ `process-content` / `publish`
- 报告：`runtime/out/reports/sichuan_full_batch_run.jsonl`

## 实现

```bash
# 可选：RUN_FULL_RESET=1、SICHUAN_SKIP_CATALOG_BUILD=1（沿用已有目录）、SICHUAN_DEEP_TOPIC_CAP、MIN_KEPT、MIN_ROWS
bash scripts/run_sichuan_province_full_batch_trinity.sh
```

## 辅助

刷新县级 `slices` 列表（检入前 diff）：

```bash
python3 quwoquan_data/tools/geo/list_admin_slices_overpass.py --province 四川省 --admin-level 6 --emit-yaml
```

## 边界

- 全量 Overpass 约 180+ 切片，耗时长；`chuanxi_attractions_catalog.yaml` 仍是 KPI-L1 小集，不是千级主目录
- 默认深链路 topic 数由 `SICHUAN_DEEP_TOPIC_CAP` 限制，避免单次对外站点压力过大
