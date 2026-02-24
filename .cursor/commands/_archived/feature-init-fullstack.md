---
name: /feature-init-fullstack
id: feature-init-fullstack
category: Workflow
description: 初始化端云一体特性目录并更新特性台账
---

在仓库根目录执行以下步骤：

1. 创建特性目录：
```bash
bash scripts/new_feature_fullstack.sh "<slug>"
```

2. 先选定特性树路径（权威）：
- 在 `changes/feature_tree.yaml` 中选择或新增节点（`feature_path` + `title`）
- 按目录层级表达父子关系（`parent_path`），优先可读性
- 同步更新 `specs/l1_index.yaml`（确保对应 L1 目录映射存在）

3. 更新 `changes/feature_catalog.yaml`（兼容索引）：
- 仍补齐兼容字段（`id/level/parent_id`）以通过现有校验
- 语义以 `changes/feature_tree.yaml` 的路径和标题为准

4. 补齐 `changes/<date>-<slug>/`：
- `README.md`
- `contracts_delta.md`
- `acceptance.yaml`
- `tasks.md`
- `traceability.yaml`
- `acceptance.yaml` 按 A1~A8 统一模板补齐
- `acceptance.yaml` 额外补齐：
  - `tree_context.feature_level`
  - `tree_context.feature_path`
  - `tree_context.parent_path`
  - `tree_context.acceptance_inherits_from`（父路径）
  - `level_acceptance.focus_groups`

5. 运行校验：
```bash
make verify
```

