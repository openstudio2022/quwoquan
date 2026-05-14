---
name: /data-baseline
id: data-baseline
category: Workflow
description: 应用数据生成工作流 · 数据规格基线阶段
---

## 目标

冻结并检查数据专题基线：

- `spec.md`
- `design.md`
- `acceptance.yaml`
- `workflow.md`
- `command-matrix.md`
- config / schema 文件

## 真实实现

对应 CLI：

```bash
python3 quwoquan_data/tools/cli.py data baseline \
  --spec-doc "<spec.md>" --design-doc "<design.md>" --acceptance-doc "<acceptance.yaml>" \
  --workflow-doc "<workflow.md>" --command-matrix-doc "<command-matrix.md>" \
  --catalog-config "<geo_catalog_config.yaml>" --naming-rules "<entity_naming_rules.yaml>" \
  --geo-band-rules "<geo_band_rules.sichuan.yaml>" \
  --schema-files <schema...>
```

说明：`--catalog-config` 与 `--geo-band-rules` **同时传入**时，CLI 会校验 `catalog.geo_band_rules_path` 相对 catalog 目录解析后的路径与 `--geo-band-rules` **完全一致**，避免基线登记与构建实际加载的地域带规则漂移。

## 输出

- 基线文件存在性与 schema/lint 结果

## 工作流位置

`data explore` → **data baseline** → `data build-entities-tags` → ...

baseline 是 explore 之后、build-entities-tags 之前的强制步骤，冻结规格和配置基线。

## 门禁

- 所有基线文件必须存在
- catalog-config 与 geo-band-rules 路径一致性校验通过
